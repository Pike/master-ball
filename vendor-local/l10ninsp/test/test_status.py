# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta

from twisted.trial import unittest
from twisted.internet import defer

from buildbot import interfaces
from buildbot.test.runutils import RunMixin

from django.conf import settings

if not settings.configured:
  settings.configure(DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3'}},
                     INSTALLED_APPS = ('life',
                                       'mbdb',
                                       'bb2mbdb',
                                       'l10nstats',
                                       ),
                     BUILDMASTER_BASE = 'basedir')

config = """
from buildbot.process import factory
from buildbot.steps import dummy
from buildbot.buildslave import BuildSlave
s = factory.s

f = factory.BuildFactory([
    s(dummy.Dummy, timeout=1),
    s(dummy.RemoteDummy, timeout=2),
    ])

BuildmasterConfig = c = {}
c['slaves'] = [BuildSlave('bot1', 'sekrit')]
c['schedulers'] = []
c['builders'] = []
c['builders'].append({'name': 'test_builder', 'slavename': 'bot1',
                      'builddir': 'dummy1', 'factory': f})
c['slavePortnum'] = 0
"""

config_2 = config + '''
from bb2mbdb.status import setupBridge
setupBridge('test-master', None, c)
'''

from django.conf import settings
from django.db import connection
from mbdb.models import *

class DatabaseStatus(RunMixin, unittest.TestCase):
  old_name = settings.DATABASE_NAME
  def setUp(self):
    self._db = connection.creation.create_test_db()
    return RunMixin.setUp(self)

  def tearDown(self):
    connection.creation.destroy_test_db(self.old_name)
    return RunMixin.tearDown(self)

  def testBuild(self):
    m = self.master
    s = m.getStatus()
    m.loadConfig(config_2)
    m.readConfig = True
    m.startService()
    d = self.connectSlave(builders=["test_builder"])
    d.addCallback(self._doBuild)
    return d

  def _doBuild(self, res):
    c = interfaces.IControl(self.master)
    d = self.requestBuild("test_builder")
    d2 = self.master.botmaster.waitUntilBuilderIdle("test_builder")
    dl = defer.DeferredList([d, d2])
    startedAround = datetime.utcnow()
    dl.addCallback(self._doneBuilding, startedAround)
    return dl

  def _doneBuilding(self, res, startedAround):
    endedAround = datetime.utcnow()
    delta = timedelta(0, 1)
    self.assertEquals(Build.objects.count(), 1)
    self.assertEquals(Builder.objects.count(), 1)
    self.assertEquals(BuildRequest.objects.count(), 1)
    self.assertEquals(Slave.objects.count(), 1)
    self.assertEquals(Master.objects.count(), 1)
    self.assertEquals(SourceStamp.objects.count(), 1)
    build = Build.objects.all()[0]
    self.assert_(abs(build.starttime-startedAround) < delta)
    self.assert_(abs(build.endtime-endedAround) < delta)
    self.assertEquals(build.getProperty('buildername'), 'test_builder')
    self.assertEquals(build.getProperty('slavename'), 'bot1')
    self.assertEquals(build.getProperty('buildnumber'), 0)
    self.assertEquals(build.reason, 'forced build')
    self.assertEquals(build.sourcestamp.changes.count(), 0)
    pass
