#! /usr/bin/env python2

"""

Copyright 2013, 2015 Kevin Cox

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.

"""

"""Auto-incrementing counters for AppEngine."""

import math
import random
import logging

from google.appengine.ext import ndb

logger = logging.getLogger('increment')
"""
	Set the logging level.  The defualt only shows major issues such
	as running out of keys.  INFO prints what each call is doing and
	debug prints a lot of info.
"""
logger.setLevel(logging.WARNING)

class IncrementCounter(ndb.Model):
	cur = ndb.IntegerProperty(indexed=False, default=0)
	max = ndb.IntegerProperty(indexed=False, default=0)

	chunk = 8 # Not stored.
	_use_memcache = False # Won't do anything.

	def _fromroot(self, num):
		global logger
		logger.info("RAISING TO MASTER!!!")
		id = self.key.string_id()
		if "__" in id:
			return IncrementCounter.get_by_id(self.key.string_id().partition("__")[0]).reserve(num)
		else:
			logger.error("Out of ids on master!")
			return False, False

	def reserve(self, num):
		global logger
		logger.debug("{} has {{cur:{},max:{}}}".format(self.key.id(), self.cur, self.max))
		if self.cur >= self.max:
			l, h = self._fromroot(num+self.chunk)
			if l is False:
				return False, False
			self.cur = l
			self.max = h

		rl = self.cur                         # Low value.
		self.cur = min(self.cur+num, 2**63-1) # Desired value. (Don't overflow)
		rh = min(self.cur, self.max)          # Actual high value.

		self.put()
		logger.info("{} reserved {},{}".format(self.key.id(), rl, rh))
		return rl, rh

	def next(self, num, guaranteed=True):
		l, h = self.reserve(num)
		if l is False:
			return False
		r = range(l,h)

		if guaranteed and len(r) < num:
			l2, h2 = self.reserve(num-len(r))
			if l2 is False:
				self.cur = l # Restore old values so we don't loose ids.
				self.max = h #
				return False
			r.extend(range(l2, h2))

		return r

	def one(self):
		return self.reserve(1)[0]

class Increment(object):
	"""
		A class for getting sequences of "eventually sequential" integers on
		Google App Engine.  It uses shading counters reserving chunks of ids
		from a master counter.

		The idea is to get sequential ids. However, to make it scale, atomic
		sequential ids can't be used.  Instead ids are reserved from a master
		in chunks and then served out.  This ensures that you are getting
		"almost" sequential ids, and that all the ids will be used eventually.

		The main design goals of this library were scalability and gap-free ids.
		This means that performance should scale horizontally with the chunk
		size (provided you have enough shards that they aren't overloaded).

		Gap-free means that no ids will be missed.  However it is important to
		note that there is no (easy) way to return ids to the counter. Once you
		ask for them they are yours (unless it is inside a transaction and you
		cancel it). In theory you could manually create a shard with the `cur`
		and `max` values covering the ids you want. You can freeze your counters
		and modify the values of an empty shard (``cur >= max``) or modify the
		values of a shard adjacent to the values you wish to return.  If you
		want to return values while live you can create a new shard with the
		proper values and update your app to use that shard.

		Adding and removing shards
		==========================
		All you have to do to add a shard is raise the `shards` parameter in the
		constructor.  The shard is automatically created the first time it is
		accessed.

		.. note::
			If you add a large number of shards in proportion to your current
			number you may get some contention on the master as they fetch their
			first chunk of ids.  If you are going to double your number of
			shards, for example, you will have half of your request hitting the
			master for a short while.  If you need to make a dramatic change
			to the number of shards consider doing it in smaller steps.

		To remove a shard you can just decrement the count but you will loose
		the values in that shard.  For how to return those values see above.

		Transactions
		============
		The shards use transactions to update atomically.  If you are in a
		trasaction it will join it and if you are not it will create one.  Each
		call will make at least one group access and possibly access the root
		node (making it two groups). Therefore if you are calling this inside of
		a transaction you will need to do a cross-group transaction.
	"""

	def __init__(self, name, chunk=0, shards=None, min=1, max=2**63-1, direct=True):
		"""
			Constructor.

			This creates an Incrementor.  It also controls some settings.  It
			is fairly cheep to set up but you may wish to cache it somewhere
			so that you don't have to provide the `name`, `chunk` and `shards`
			values all over your code.

			Args:
				name (str):
					A name for this counter.  It can be anything as long as it
					doesn't contain a double underscore "__".  If a counter for
					this name doesn't exist it is created, if it already exists
					it will be used.

					This defaults to zero so that ``Increment("name").delete()``
					works.  If you have a chunk size of zero it will effectively
					disabling batch fetching, defeating the purpose of the
					counters (expect that it becomes easy to scale later).

			Kwargs:
				chunk (int):
					The chunk fetch size.  This is local to the python object,
					this means that if a call to this instance requires a fetch
					from master the shard will reserve this many extra ids.

					There is no speed downside to setting this larger, it just
					means that your ids may be further apart when created.  This
					value is what controls the load on the master.  If you have
					contention on the master this should be raised.
				shards (int):
					The number of shards to use.  By default it is related to
					the value of `chunk`.  Currently it is `chunk` plus the log
					of `chunk` to the base 2.  In a perfect world it could be
					equal to the chunk size but if a number of shards run out
					of ids at the same time they will all go to the master.  If
					there is contention on the shards this value should be
					raised.

					If this value is ``0`` the root node will be accessed
					directly each time.  This may be used for small loads so
					that you can scale later as you need to.  Note that setting
					this to ``1`` is just a waste of resources.
				min (int):
					The lowest id to serve.  This only has effect when creating
					the counter.  If "connecting" to an existing counter it is
					ignored. This defaults to one because that is the lowest
					key id appengine supports.
				max (int):
					The highest id to serve.  This defaults to the largest
					possible 32-bit integer.  This only has effect when creating
					the counter.  If "connecting" to an existing counter it is
					ignored.
				direct (bool):
					If set, request for more ids then the chunk size are passed
					directly to the master rather then being passed through a
					slave.  It is recommended to leave this set as you will hit
					one entity rather than two.  If unset `reserve()` has a
					lower chance of returning enough ids for large request.
					That being said you should rarely be making request larger
					then the chunk size as it defeats the purpose of the
					sharding.
		"""
		root = IncrementCounter.get_or_insert(name, cur=min, max=max)

		self.name = name
		"""
			The counter name.  All counters with the same name will use the same
			pool of IDs.  If this is changed all values from `randomshard()`
			become invalid and will lead to undefined behaviour if used again.
		"""
		self.rootkey = root.key
		self.chunk = chunk
		"""
			The chunk size.  This takes affect immediately.  You may wish to
			raise this value if you know you are going to make many request
			later but you can't allocate all the IDs up front because you don't
			know how many you will need.
		"""
		self.shards = shards
		# Unnecessarily complex guess of how many shards you should have.
		if shards is None:
			if chunk:
				self.shards = chunk+int(math.log(chunk)/math.log(2))
			else:
				self.shards = 0
		"""
			The number of shards.  This takes affect immediately.  Read the
			section above about adding or removing shards.
		"""
		self.direct = direct
		"""
			Whether to allow direct calls to the root node. This takes affect
			immediately.
		"""

		logging.info("Counter name: {}".format(self.name))
		logging.info("Chunk size: {}".format(self.chunk))
		logging.info("Number of shards: {}".format(self.shards))
		logging.info("Allow Direct: {}".format(self.direct))

	def randomshard(self):
		"""
			Returns a shard name.  This should be treated as opaque and can
			be passed to the `shard` parameter of the id retrieval functions.
			This is useful when you want to fetch ids in batches inside a
			transaction.  If you picked a random shard each time you would
			access many entity groups but if you use the same shard for all
			lookups inside a transaction you will access a maximum of two.

			Returns:
				(string):
					The shard name.
		"""
		if self.shards <= 0: # No shards, go to root.
			return self.name

		return self.name+"__"+str(random.randint(1,self.shards))

	def _getshard(self, num=0, shard=None, chunk=None):
		if shard is None:
			shard = self.randomshard()
		if chunk is None:
			chunk = self.chunk

		# Handle direct-to-root.
		if self.direct and num >= chunk:
			logging.debug("Using {}".format(self.rootkey.string_id()))
			return self.rootkey.get()

		# Use a shard.
		logging.debug("Using {}".format(shard))
		s = IncrementCounter.get_or_insert(shard)
		s.chunk = chunk # Let it know our preferences.
		return s

	@ndb.transactional(propagation=ndb.TransactionOptions.ALLOWED, xg=True)
	def reserve(self, num, shard=None, chunk=None):
		"""
			Reserve a sequence of ids.

			Args:
				num (int):
					The largest number of ids to reserve.

			Kwargs:
				shard (string):
					A value from `randomshard()`.  Use this shard.  If not provided
					a random shard is picked for you.
				chunk (int):
					The chunk size to use if this call requires a fetch to
					master.  This also affects making direct calls to the
					master.

			Returns:
				(int, int):
					Returns lowest, and one past the highest id reserved.  These
					are such that ``range(inc.reserve(num))`` would return a
					list of the reserved ids.

				(False, False):
					Returns ``False`` if there are no ids available.  This means
					that the root node has no ids left.

					.. note::
						You will not necessarily get the number of ids you ask
						for.  This will not go up to the root node unless the
						shard is empty, this is because there is a slim chance
						that the new ids retrieved would be sequential to the
						shard already has.
		"""
		if num <= 0:
			return 0,0
		return self._getshard(num=num, shard=shard, chunk=chunk).reserve(num)

	@ndb.transactional(propagation=ndb.TransactionOptions.ALLOWED, xg=True)
	def next(self, num, guaranteed=True, shard=None, chunk=None):
		"""
			Returns a list of ids.

			Args:
				num (int):
					The number of ids to retrieve.

			Kwargs:
				guaranteed (bool):
					Try to get all num ids.  This means that if the shard
					doesn't have enough more ids will be requested from master.

					.. warning::
						Having guaranteed `True` means that the ids may not be
						sequential.  Having guaranteed `False` means that you
						may not get the amount that you asked for.

						`True` also may not return the correct number if the
						master doesn't have enough ids left to complete the
						request.  This is so that ids aren't lost.
				shard, chunk:
					See `reserve()`.

			Returns:
				list:
					A list of the ids.
				False:
					False is returned if there are no ids available.  This means
					that the root node has no ids left.

		"""
		if num <= 0:
			return []
		return self._getshard(num=num, shard=shard, chunk=chunk).next(num, guaranteed)

	@ndb.transactional(propagation=ndb.TransactionOptions.ALLOWED, xg=True)
	def one(self, shard=None, chunk=None):
		"""
			Return one id.

			Kwargs:
				shard, chunk:
					See `reserve()`.

			Returns:
				int:
					The id.
				False:
					False is returned if there are no ids available.  This means
					that the root node has no ids left.
		"""
		return self._getshard(num=1, shard=shard, chunk=chunk).one()

	@ndb.toplevel
	def delete(self):
		"""
			Deletes all shards and the master associated with this counter.

			All instances using this counter can not be used any more.  If they
			are recreated they will recreate the counter the same way they would
			with a never-used-before name.

			You have to be very careful when using this on "live" counters.  You
			need to first ensure everyone stops accessing the counter and
			deletes their `Increment` instances.  It is mainly intended for
			admin action and manual use.

			.. note::
				Note that this does not take the `shards` value into account, it
				removes all shards matching the name pattern.
		"""
		q = (IncrementCounter.query()
		       .filter(IncrementCounter.key > ndb.Key(IncrementCounter,self.name+"__"))
		       .filter(IncrementCounter.key < ndb.Key(IncrementCounter,self.name+"__A"))
		    )

		self.rootkey.delete_async()
		ndb.delete_multi(q.iter(keys_only=True))
