#! /usr/bin/env python2

"""

Copyright 2013 Kevin Cox

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

from google.appengine.ext import db

class IncrementCounter(db.Model):
	cur = db.IntegerProperty(indexed=False, default=0)
	max = db.IntegerProperty(indexed=False, default=0)

	chunk = 8 # Not stored.

	readfrommaster = False # Make sure we don't read old data inside a transaction.
	def _fromparent(self, num):
		if ( not self.readfrommaster ) and self.parent_key():
			p = IncrementCounter.get(self.parent_key())
			self.readfrommaster = True
			return p.reserve(num)
		else:
			return False, False

	def reserve(self, num):
		if self.cur >= self.max:
			l, h = self._fromparent(num+self.chunk)
			if l is False:
				return False, False
			self.cur = l
			self.max = h

		rl = self.cur                         # Low value.
		self.cur = min(self.cur+num, 2**63-1) # Desired value. (Don't overflow)
		rh = min(self.cur, self.max)          # Actual high value.

		self.put()
		return rl, rh

	def next(self, num, guaranteed=True):
		l, h = self.reserve(num)
		print(l,h)
		if l is False:
			return False
		r = range(l,h)
		print(r)

		if guaranteed:
			l2, h2 = self.reserve(num-len(r))
			print(l2,h2)
			if l2 is False:
				self.cur = l # Restore old values so we don't loose ids.
				self.maz = h #
				return False
			r.extend(range(l2, h2))

		return r

	def one(self):
		return self.reserve(1)[0]


class Increment(object):
	"""
		A class for getting sequences of "eventually sequential integers on
		Google App Engine.  It uses shading counters reserving chunks of ids
		from a master counter.

		The idea is to get sequential ids, but to make it scale atomicaly
		sequential ids can't be used.  Instead ids are reserved from a master
		in chunks and then served out.  This ensures that you are getting
		"almost" sequential ids, and that all the ids will be used.

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

		To remove a shard you can just decrement the count but you will loose
		the values in that shard.  For how to return those values see above.

		Transactions
		============
		The shards use transactions to update atomically.  If you are in a
		trasaction it will join it and if you are not it will create one.  The
		library is smart enough not to mess up inside its own transactions but
		if you are calling it from a transaction you have to ensure you only
		make one request to any counter (not per-instance, any counter with the
		same name) or you risk getting the same id multiple times.  This is
		because we will not read our writes until the trasaction ends and there
		is no way for us to tell what the state "inside" the transaction result
		is.  Until App Engine supports `propagation=NESTED` transactions this
		limitation will persist (and that might not even solve the problem).

		Testing
		=======
		As of now this library has been *lightly* tested and has not been tested
		at a high load.  For a test of "eventually sequential" see the results
		here (http://pastebin.com/p8cMSpzy).  This is a test where random calls
		were made and the results show how all of lower numbers are sequential
		while the highest ones have gaps.

		Limitations
		===========
		 - Only one request per transaction.
		 - Fixed id sequence (always going up by ones).  This can be mitigated
		   by modifing the results (ex: multiply by two for incrementing by 2 or
		   subtract from a max number to go down).
	"""

	def __init__(self, name, chunk=2, shards=None, min=0, max=2**63-1, direct=True):
		IncrementCounter.get_or_insert(name, cur=min, max=max)
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

			Kwargs:
				chunk (int):
					The chunk size, this currently defaults to ``2``, you should
					probably change that.  This is local to the python object,
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
				min (int):
					The lowest id to serve.  This only has effect when creating
					the counter.  If "connecting" to an existing counter it is
					ignored.
					raised.
				min (int):
					The highest id to serve.  This defaults to the largest
					possible 32-bit integer.  This only has effect when creating
					the counter.  If "connecting" to an existing counter it is
					ignored.
				direct (bool):
					If set request for more ids then the chunk size are passed
					directly to the master rather then being passed through a
					slave.  It is recommended to leave this set as you will hit
					one entity rather than two.  If unset `reserve()` has a
					lower chance of returning enough ids for large request.
					That being said you should rarely be making request larger
					then the chunk size as it defeats the purpose of the
					sharding.
		"""

		self.name = name
		self.rootkey = db.Key.from_path("IncrementCounter", name)
		self.min = min
		self.chunk = chunk
		# Unnecessarily complex guess of how many shards you should have.
		self.shards = shards or chunk+int(math.log(chunk)/math.log(2))
		self.direct = direct

		#logging.debug("Chunk size: {}".format(self.chunk))
		#logging.debug("Number of shards: {}".format(self.shards))

	def _rootshard(self):
		#logging.debug("Dropping to root.")
		return IncrementCounter.get(self.rootkey)

	def _randomshardname(self):
		return self.name+"__"+str(random.randint(1,self.shards))

	def _randomshard(self):
		sn = self._randomshardname()
		#logging.debug("Using {}".format(sn))
		s = IncrementCounter.get_by_key_name(sn, parent=self.rootkey)

		if s is None:
			s = IncrementCounter(key_name=sn, parent=self.rootkey)

		s.chunk = self.chunk # Let it know our preferences.
		return s

	@db.transactional(propagation=db.ALLOWED)
	def reserve(self, num):
		"""
			Reserve a sequence of ids.

			Args:
				num (int):
					The largest number of ids to reserve.

			Returns:
				(int, int):
					Returns lowest, and one past the highest id reserve.  These
					are such that ``rance(inc.reserve(num))`` would return a
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
		if self.direct and num > self.chunk:
			s = self._rootshard()
		else:
			s = self._randomshard()

		return s.reserve(num)

	@db.transactional(propagation=db.ALLOWED)
	def next(self, num, guaranteed=True):
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

			Returns:
				list:
					A list of the ids.
				False:
					False is returned if there are no ids available.  This means
					that the root node has no ids left.

		"""
		if self.direct and num > self.chunk:
			s = self._rootshard()
		else:
			s = self._randomshard()

		return s.next(num, guaranteed)

	@db.transactional(propagation=db.ALLOWED)
	def one(self):
		"""
			Return one id.

			Returns:
				int:
					The id.
				False:
					False is returned if there are no ids available.  This means
					that the root node has no ids left.
		"""
		return self._randomshard().one()
