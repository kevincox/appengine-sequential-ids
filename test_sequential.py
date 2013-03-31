#! /usr/bin/python

import os, sys
import random
import pprint

from google.appengine.api import memcache
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
import trade
import increment

#for e in db.GqlQuery("SELECT * FROM IncrementCounter"):
#  e.delete()

inc = increment.Increment("test", 5, min=0)
results = set()

def trytoadd(ids):
	for id in ids:
		if id in results:
			print "ERROR: Got id twice", id
		results.add(id)

for _ in xrange(1000):
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
