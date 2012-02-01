While working on the [ASU Digital Repository](http://repository.asu.edu/), I found I needed the ability to trigger
callbacks when a transaction was committed.  Django's signals seemed to be the perfect mechanism, but transaction commit and rollback signals are not (as of this writing) supported in the core framework.  (See these tickets in the Django issue tracker for background: [Ticket #14050](https://code.djangoproject.com/ticket/14050), 
[Ticket #14051](https://code.djangoproject.com/ticket/14051))

However, [a gist](https://gist.github.com/247844) written by [Grégoire Cachet](https://github.com/gcachet) seems to do the trick.  It adds a custom signal implementation and monkey-patches Django's transaction handling functions to dispatch **post_commit** and **post_rollback** signals. 

This module extends that gist in the following ways:

+ Adds a **defer()** function that can be used inside a transaction to defer the execution of a function until the   transaction has committed (I found this quite useful for triggering [Celery](https://github.com/ask/celery) tasks that depend on the objects committed).
+ Guards against badly behaved signal handlers (i.e. ones that leave the current transaction in a dirty state) and raises a BadlyBehavedTransactionSignalHandlerError when it detects a misbehaving handler.
+ Clears handlers on transaction exit regardless of whether a commit, rollback, or neither occurred.  This fixes an issue where handlers could accumulate and be triggered on a subsequent transaction. 

### Usage (from the original gist):

__*You have to make sure to load this before you use signals.*__

For example, add the the following line to your project's **\_\_init\_\_**.py file:

```python
import django_transaction_signals.transaction
```
 
Then, to use the signals, create a function and bind it to the **post_commit** signal:

```python
from django.db import transaction

def my_function(**kwargs):
   # do your stuff here
   pass
transaction.signals.post_commit.connect(my_function)
```

If you're using non-local variables in your callback function, make sure to use non-weak reference or your variables could be garbage collected before the function gets called. For example, in a model's **save()** method:

```python
def save(self, *args, **kwargs):
    def my_function(**kwargs):
        # do your stuff here
        # access self variable
        self
    transaction.signals.post_commit.connect(my_function, weak=False)
```

### Usage of defer() function:
This demonstrates a transactional update of a model object which registers a Celery task to be executed when the transaction commits successfully.

```python
from celery.task import task
from django.db import transaction
from django_transaction_signals import defer
import pysolr

@transaction.commit_on_success
def update_object(obj):
    # ...modify and save object...
    defer(index_object.delay, obj)
    # ...do some additional work in the transaction...
    
@task
def index_object(obj):
    index_obj = {'id': obj.id}
    # ...build index object...
    solr = pysolr.Solr('http://localhost:8080/solr')
    solr.add([index_obj])
```