While working on the [ASU Digital Repository](http://repository.asu.edu/), I found I needed the ability to trigger
callbacks when a transaction was committed.  Django's signals seemed to be the perfect mechanism, but transaction commit 
and rollback signals are not (as of this writing) supported in the core framework.  (See these tickets in the Django
issue tracker for background: [Ticket #14050](https://code.djangoproject.com/ticket/14050), 
[Ticket #14051](https://code.djangoproject.com/ticket/14051))

However, [a gist](https://gist.github.com/247844) written by [Grégoire Cachet](https://github.com/gcachet)
seems to do the trick.  This module is an extension of his work.

In addition to the base signals, I added a **defer()** function that can be used inside a transaction to defer the 
execution of a function until the transaction has committed (I found this quite useful for triggering 
[Celery](https://github.com/ask/celery) tasks that depend on the objects committed).

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

If you're using non-local variables in your callback function, make sure to
use non-weak reference or your variables could be garbage collected before
the function gets called. For example, in a model's **save()** method:

```python
 def save(self, *args, **kwargs):
     def my_function(**kwargs):
         # do your stuff here
         # access self variable
         self
     transaction.signals.post_commit.connect(my_function, weak=False)
```

### Usage of defer() function:

```python
 from mymodule.tasks import mytask
 
 @transaction.commit_on_success
 def another_function(**kwargs):
   # update something
  defer(mytask)(arg1, arg2, kwarg1='...')
  # update something else
```