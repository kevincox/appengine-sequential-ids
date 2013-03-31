#! /usr/bin/python

import random
import logging
import increment

increment.logger.setLevel(logging.DEBUG)

#for e in db.GqlQuery("SELECT * FROM IncrementCounter"):
#  e.delete()

def run(rounds=1000, name="test", chunk=7, **kwargs):
	inc = increment.Increment(name, chunk, min=0, **kwargs)
	results = set()

	def trytoadd(ids):
		for id in ids:
			if id in results:
				print "ERROR: Got id twice", id
			results.add(id)

	for _ in xrange(rounds):
		r = random.randint(0,2)
		if r == 0:
			res = inc.next(random.randint(0,9))
			print "Used next() to get", res
			trytoadd(res)
		if r == 1:
			l, h = inc.reserve(random.randint(0,9))
			print "Used reserve() to get", l, h
			trytoadd(range(l,h))
		if r == 2:
			res = inc.one()
			print "Used one() to get", res
			trytoadd([res])

	for id in xrange(max(results)):
		if id not in results:
			print "Missing", id
