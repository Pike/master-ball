# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from buildbot.changes.changes import Change
from buildbot.status import builder as builderstatus
from twisted.trial import unittest
from twisted.application import service
from twisted.internet import reactor, defer
from twisted.spread import pb

from l10ninsp import scheduler
import l10ninsp.logger
l10ninsp.logger.init(
    scheduler=l10ninsp.logger.DEBUG
)


# copied from buildbot.test.test_scheduler
class FakeMaster(service.MultiService):
    d = None

    def submitBuildSet(self, bs):
        self.sets.append(bs)
        if self.d:
            reactor.callLater(0, self.d.callback, bs)
            self.d = None
        return pb.Referenceable()  # makes the cleanup work correctly


# copied from buildbot.test.test_buildreq
class FakeBuilder:
    def __init__(self, name):
        self.name = name
        self.requests = []

    def submitBuildRequest(self, req):
        self.requests.append(req)


class AppScheduler(unittest.TestCase):
    def setUp(self):
        self.master = master = FakeMaster()
        master.sets = []
        master.startService()

    def tearDown(self):
        d = self.master.stopService()
        return d

    def addScheduler(self, name, builderNames, inipath, treebuildername):
        s = scheduler.AppScheduler(
            name, builderNames, inipath, treebuildername)
        s.setServiceParent(self.master)
        self.scheduler = s

    def setupSimple(self):
        self.addScheduler('test-sched', ['compare'], None, 'tree-builds')
        t = scheduler.Tree('test', 'http://localhost/', 'test-branch',
                           'l10n-test', 'test-app/locales/l10n.ini')
        t.addData('test-branch', 'test-app/locales/l10n.ini',
                  ['test-app'])
        t.locales += ['de', 'fr']
        self.scheduler.addTree(t)

    def test_a_L10n(self):
        self.setupSimple()
        c = Change('author', ['test-app/file.dtd'], 'comment',
                   branch='l10n-test', properties={'locale': 'de'})
        c.number = 1
        self.scheduler.addChange(c)
        self.failUnless(self.scheduler.dSubmitBuildsets)
        self.scheduler.dSubmitBuildsets.cancel()
        pendings = self.scheduler.pendings
        self.failUnlessEqual(len(pendings), 1)

    def test_b_EnUS(self):
        self.setupSimple()
        c = Change('author', ['test-app/locales/en-US/file.dtd'], 'comment',
                   branch='test-branch')
        c.number = 1
        self.scheduler.addChange(c)
        self.failUnless(self.scheduler.dSubmitBuildsets)
        self.scheduler.dSubmitBuildsets.cancel()
        pendings = self.scheduler.pendings
        self.failUnlessEqual(len(pendings), 2)

    def test_c_mixed(self):
        self.setupSimple()
        c = Change('author', ['test-app/locales/en-US/file.dtd'], 'comment',
                   branch='test-branch')
        c.number = 1
        self.scheduler.addChange(c)
        c = Change('author', ['test-app/file.dtd'], 'comment',
                   branch='l10n-test', properties={'locale': 'de'})
        c.number = 2
        self.scheduler.addChange(c)
        self.failUnless(self.scheduler.dSubmitBuildsets)
        self.scheduler.dSubmitBuildsets.cancel()
        pendings = self.scheduler.pendings
        self.failUnlessEqual(len(pendings), 2)
        self.failUnlessEqual(len(pendings[('test', 'de')]), 2)
        self.failUnlessEqual(len(pendings[('test', 'fr')]), 1)

    def test_d_ini(self):
        self.setupSimple()
        c = Change('author', ['test-app/locales/l10n.ini'], 'comment',
                   branch='test-branch')
        c.number = 1
        self.scheduler.addChange(c)
        c = Change('author', ['test-app/locales/en-US/app.dtd'], 'comment',
                   branch='test-branch')
        c.number = 2
        self.scheduler.addChange(c)
        self.failUnlessEqual(len(self.master.sets), 1)
        bset = self.master.sets[0]
        self.failUnlessEqual(bset.builderNames, ['tree-builds'])
        ftb = FakeBuilder('tree-builds')
        bset.start([ftb])
        self.failUnlessEqual(len(ftb.requests), 1)
        st = bset.status
        self.failIf(st.isFinished())
        builder = builderstatus.BuilderStatus('tree-builds')
        build = builderstatus.BuildStatus(builder, 1)
        build.setResults(builderstatus.SUCCESS)
        ftb.requests[0].finished(build)
        self.failUnless(st.isFinished())
        self.failUnless(self.scheduler.dSubmitBuildsets)
        self.scheduler.dSubmitBuildsets.cancel()
        pendings = self.scheduler.pendings
        self.failUnlessEqual(len(pendings), 2)
        self.failUnlessEqual(len(pendings[('test', 'de')]), 1)
        self.failUnlessEqual(len(pendings[('test', 'fr')]), 1)
