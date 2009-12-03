# post_commit and post_rollback transaction signals for Django with monkey patching
# Author Grégoire Cachet <gregoire.cachet@gmail.com>

from django.db import transaction
from django.dispatch import Signal

try:
    import thread
except ImportError:
    import dummy_thread as thread
    
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
        if thread_ident not in self.signals:
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
    
    @property
    def post_commit(self):
        return self._get_or_init_signals().post_commit
        
    @property
    def post_rollback(self):
        return self._get_or_init_signals().post_rollback
        
transaction.signals = TransactionSignals()

# monkey patching
old_enter_transaction_management = transaction.enter_transaction_management
def enter_transaction_management(*args, **kwargs):
    old_enter_transaction_management(*args, **kwargs)
    transaction.signals._init_signals()
transaction.enter_transaction_management = enter_transaction_management

old_leave_transaction_management = transaction.leave_transaction_management
def leave_transaction_management(*args, **kwargs):
    old_leave_transaction_management(*args, **kwargs)
    transaction.signals._remove_signals()
transaction.leave_transaction_management = leave_transaction_management
    
old_managed = transaction.managed
def managed(flag=True):
    to_commit = False
    if not flag and transaction.is_dirty():
        to_commit = True
    old_managed(flag)
    if to_commit:
        transaction.signals.post_commit.send(sender=transaction)
transaction.managed = managed

old_commit_unless_managed = transaction.commit_unless_managed
def commit_unless_managed(*args, **kwargs):
    old_commit_unless_managed(*args, **kwargs)
    if not transaction.is_managed():
        transaction.signals.post_commit.send(sender=transaction)
transaction.commit_unless_managed = commit_unless_managed

old_rollback_unless_managed = transaction.rollback_unless_managed
def rollback_unless_managed(*args, **kwargs):
    old_rollback_unless_managed(*args, **kwargs)
    if not transaction.is_managed():
        transaction.signals.post_rollback.send(sender=transaction)
transaction.rollback_unless_managed = rollback_unless_managed

old_commit = transaction.commit
def commit(*args, **kwargs):
    old_commit(*args, **kwargs)
    transaction.signals.post_commit.send(sender=transaction)
    old_commit(*args, **kwargs)
transaction.commit = commit

old_rollback = transaction.rollback
def rollback(*args, **kwargs):
    old_rollback(*args, **kwargs)
    transaction.signals.post_rollback.send(sender=transaction)
    old_rollback(*args, **kwargs) # If post_rollback signals wants to commit,
                                  # it must do it by itself
transaction.rollback = rollback