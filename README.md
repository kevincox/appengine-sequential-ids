# "Eventually Sequential" IDs for App Engine

A scaleable, sharded apprach to generating sequential IDs on Google App Engine.

Lots of documentation in the source.  Feel free to
[kevincox.ca@gmail.com](email me) with questions and please submit issues in the
tracker.

## Example

```python
import increment

# Create a counter called "user-id" with a chunk size of 10.  This can
# always be raised later. (Just change that one line)  No other arguments are
# nessary as the default values match appengine's keyspace.
useridcounter = increment.Increment("user-id", 10)

# Retrieving a single id.
uid = useridcounter.one()
if uid is False:
	logging.error("Oh No!  We have run out of keys!")
	return
u1 = User(key=db.Key.from_path("User", uid))

# Now lets make ten users the hard way.
users1 = []
while len(users1) < 10:
	low, high = useridcounter.reserve(10-len(users1))
	if low is False: # High will also be false on an error, but you only need one.
		logging.error("Oh No!  We have run out of keys!")
		return
	# Note: `high-low` might NOT be 10! (read the docs)
	while low < high:
		users1.push(User(key=db.Key.from_path("User", low)))
		low += 1

# Create the counter again for completeness.  The min and max values have no
# affect as the counter has already been created (with the default min and
# max) at the top of the script (or another time, they are persistant).  Note
# that all other settings DO take affect.  When a shard is accessed using this
# object it will use this chunk size (12), NOT one set earlier on.
useridcounter = increment.Increment("user-id", 12, min=-172, max=500)

# Now the easy way.
users2 = []
ids = useridcounter.next(10)
if ids is False or len(ids) < 10: # Whereas in the hard way getting less then
	                              # ten is common, this time in only happens
	                              # if we are out of keys.
	logging.error("Oh No!  We have run out of keys!")
	return
for id in ids:
	users2.push(User(key=db.Key.from_path("User", id)))
```

Those are the three ways to get ids.  `.one()` is really easy and likely the
most common, `.reserve()` probably shouldn't be used by user code as it commonly
won't get the requested number of ids (see the in source docs for more info).
`.next()` is the easiest way to get a lot of keys, it tries its hardest to get
you the number you asked for.  See the docs for the rare cases where it fails.

I have error checking for completeness but the only times when these functions
fail (except for `.reserve()` which commonly doesn't return enough items) is
when there is too much contention in the datastore (raise the chunk size and
number of shards as appropriate to relieve this pressure) in which case it
raises an exception, or if you are out of ids on the master and the shard you
accessed they return `False` or `(False,False)` (there may still be a couple of
ids on other shards but this is generally a really bad thing).
