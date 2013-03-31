"""
	Simple test of scalibility.  You can set the paremeters from the query
	string.  It performs 5 random ID operations per request.

	There is a line in ``app.yaml`` that would add a handler.
"""

import random
import logging
import webapp2
import increment

increment.logger.setLevel(logging.DEBUG)

class test(webapp2.RequestHandler):
	def get(self):
		self.response.headers["Content-Type"] = "text/plain"

		chunk  = long(self.request.GET["chunk"])
		shards = long(self.request.get("shards", 0)) or None
		max    = long(self.request.get("size", 10))

		inc = increment.Increment("test", chunk, shards)

		for _ in xrange(10):
			num = random.randint(0,max)
			self.response.write("Trying to get"+str(num)+" ids.\n")

			r = random.randint(0,2)
			if r == 0:
				res = inc.next(num)
				self.response.write("Used next() to get "+str(res)+"\n")
			if r == 1:
				l, h = inc.reserve(num)
				self.response.write("Used reserve() to get "+str(l)+" "+str(h)+"\n")
			if r == 2:
				res = inc.one()
				self.response.write("Used one() to get "+str(res)+"\n")

app = webapp2.WSGIApplication(debug=True)
app.router.add(("/test", test))
