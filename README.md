# "Eventually Sequential" IDs for App Engine

A scaleable, sharded apprach to generating sequential IDs on Google App Engine.

Lots of documentation in the source.  Feel free to
[email me](kevincox@kevincox.ca) with questions and please submit issues in the
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
u1 = User(id=uid)

# Now lets make ten users the hard way.
users1 = []
while len(users1) < 10:
    low, high = useridcounter.reserve(10-len(users1))
    if low is False: # High will also be false on an error.
        logging.error("Oh No!  We have run out of keys!")
        return
    # Note: `high-low` might NOT be 10! (read the docs)
    while low < high:
        users1.push(User(id=low))
        low += 1

# Create the counter again for the sake of the example.  The min and max values
# have no affect as the counter has already been created (with the default min
# and max) at the top of the script (or another time, they are persistant).  Note
# that all other settings DO take affect.  When a shard is accessed using this
# object it will use this chunk size (12), NOT one set earlier on.
useridcounter = increment.Increment("user-id", 12, min=-172, max=500)

# Now the easy way.
users2 = []
ids = useridcounter.next(10)
if ids is False or len(ids) < 10: # Whereas in the hard way getting less then
                                  # ten is common, this time it only happens
                                  # if we are out of keys.
    logging.error("Oh No!  We have run out of keys!")
    return
for id in ids:
    users2.push(User(id=id))

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


## Testing

For a test of "eventually sequential" see the results here
(http://pastebin.com/p8cMSpzy).  This is a test where random calls were made
and the results show how all of lower numbers are sequential while the
highest ones have gaps.

I have done a simple benchmark live on app engine and I got about 10qps with
a chunk size of two and random request size (often requiring a fetch to the
master) before hitting contention problems.  I then turned the chunk size up
to 10 and got about 25qps.  This is still quite low as many request required
a fetch to the master.  When I turned the chunk size to 100 I got up to
100qps without any signs of contention.  I would expect this trent to
continue for higher chunk values.  The benchmark used is contained in
`test_scale.py`.
