# -*- coding: utf-8 -*-
# post_commit and post_rollback transaction signals for Django with monkey patching
# Author Grégoire Cachet <gregoire.cachet@gmail.com>
# http://gist.github.com/247844
# 
# Usage:
# You have to make sure to load this before you use signals.
# For example, create utils/__init__.py and then utils/transaction.py contening 
# this gist in you project. Then add "import utils.transaction" in your project
# __init__.py file
# 
# Then, to use the signals, create a function and bind it to the post_commit
# signal:
# 
# from django.db import transaction
# 
# def my_function(**kwargs):
#     # do your stuff here
#     pass
# transaction.signals.post_commit.connect(my_function)
# 
# If you're using non-local variables in your callback function, make sure to
# use non-weak reference or your variables could be garbarge collected before
# the function gets called. For example, in a model save() method:
# 
# def save(self, *args, **kwargs):
#     def my_function(**kwargs):
#         # do your stuff here
#         # access self variable
#         self
#     transaction.signals.post_commit.connect(my_function, weak=False)
from functools import wraps
from django.db import transaction
from django.dispatch import Signal

try:
    import thread
except ImportError:
    import dummy_thread as thread
    
class BadlyBehavedTransactionSignalHandlerError(Exception):
    '''
    Exception raised when a post_commit or post_rollback handler updates the
    current transaction and doesn't perform its own commit/rollback.  This is
    usually easily mitigated by using a wrapper like @commit_on_success. Also
    see the defer() function in this module for another approach that avoids
    this error.
    '''
    pass

class ThreadSignals(object):
    
    def __init__(self):
        self.post_commit = Signal()
        self.post_rollback = Signal()

class TransactionSignals(object):
    signals = {}
    
    def _has_signals(self):
        thread_ident = thread.get_ident()
        return thread_ident in self.signals
    
    def _init_signals(self):
        thread_ident = thread.get_ident()
        assert thread_ident not in self.signals
        self.signals[thread_ident] = ThreadSignals()
        return self.signals[thread_ident]
        
    def _remove_signals(self):
        thread_ident = thread.get_ident()
        assert thread_ident in self.signals
        del self.signals[thread_ident]
    
    def _get_signals(self):
        thread_ident = thread.get_ident()
        assert thread_ident in self.signals
        return self.signals[thread_ident]
        
    def _get_or_init_signals(self):
        if self._has_signals():
            return self._get_signals()
        else:
            return self._init_signals()
            
    def _send_post_commit(self):
        if self._has_signals():
            _signals = self._get_signals()
            self._remove_signals() 
            _signals.post_commit.send(sender=transaction)
            
            # Take care of badly behaved signal handlers that have
            # dirtied the transaction without committing properly
            if transaction.is_dirty():
                raise BadlyBehavedTransactionSignalHandlerError
    
    def _send_post_rollback(self):
        if self._has_signals():
            _signals = self._get_signals()
            self._remove_signals() 
            _signals.post_rollback.send(sender=transaction)

            # Take care of badly behaved signal handlers that have
            # dirtied the transaction without committing properly
            if transaction.is_dirty():
                raise BadlyBehavedTransactionSignalHandlerError

    def _on_exit_without_update(self):
        '''
        Clear signals on transaction exit, even if neither commit nor rollback
        happened.
        '''
        if self._has_signals():
            self._remove_signals()
    
    @property
    def post_commit(self):
        return self._get_or_init_signals().post_commit
        
    @property
    def post_rollback(self):
        return self._get_or_init_signals().post_rollback

    
transaction.signals = TransactionSignals()

old_managed = transaction.managed
def managed(*args, **kwargs):
    to_commit = False
    flag = kwargs.get('flag', True)
    if not flag and transaction.is_dirty():
        to_commit = True
    old_managed(flag)
    if to_commit:
        transaction.signals._send_post_commit()
    else:
        transaction.signals._on_exit_without_update()
transaction.managed = managed


old_commit_unless_managed = transaction.commit_unless_managed
def commit_unless_managed(*args, **kwargs):
    old_commit_unless_managed(*args, **kwargs)
    if not transaction.is_managed():
        transaction.signals._send_post_commit()
transaction.commit_unless_managed = commit_unless_managed

old_rollback_unless_managed = transaction.rollback_unless_managed
def rollback_unless_managed(*args, **kwargs):
    old_rollback_unless_managed(*args, **kwargs)
    if not transaction.is_managed():
        transaction.signals._send_post_rollback()
transaction.rollback_unless_managed = rollback_unless_managed

# If post_commit or post_rollback signals set the transaction to dirty state
# they must commit or rollback by themselves

old_commit = transaction.commit
def commit(*args, **kwargs):
    old_commit(*args, **kwargs)
    transaction.signals._send_post_commit()
transaction.commit = commit


old_rollback = transaction.rollback
def rollback(*args, **kwargs):
    old_rollback(*args, **kwargs)
    transaction.signals._send_post_rollback()                                  
transaction.rollback = rollback


def defer(f, *args, **kwargs):
    '''
    Wrapper that defers a function's execution until the current transaction
    commits, if a transaction is active.  Otherwise, executes as usual. Note 
    that a deferred function will NOT be called if the transaction completes
    without committing (e.g. when transaction.is_dirty() is False upon exiting
    the transaction).

    An implicit assumption is that a deferred function does not return an
    important value, since there is no way to retrieve the return value in
    the normal execution order.

    Before being connected to the 'post_commit' signal of an existing managed
    transaction, the deferred function is wrapped by the @commit_on_success
    decorator to ensure that it behaves properly by committing or rolling back
    any updates it makes to a current transaction.
    
    >>> def log_success(msg):
    >>>     print 'logging success'
    >>>     LOG.info(msg)
    >>>
    >>> @transaction.commit_on_success    
    >>> def transactional_update(value)
    >>>     print 'starting transaction'
    >>>     ... perform update ...
    >>>     defer(log_success, 'The transaction was successful')
    >>>     print 'finishing transaction'
    >>>
    >>> transactional_update('foo')
    ... starting transaction
    ... finishing transaction
    ... logging success
    '''
    if transaction.is_managed():
        @transaction.commit_on_success
        def f_deferred(*a, **kw):
            f(*args, **kwargs)
        transaction.signals.post_commit.connect(f_deferred, weak=False)
    else:
        f(*args, **kwargs)
