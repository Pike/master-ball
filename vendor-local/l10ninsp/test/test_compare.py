# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# test step.ShellCommand and the slave-side commands.ShellCommand

import sys, time, os
from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.python import util, log
from l10ninsp.slave import InspectCommand, InspectDirsCommand
from buildbot import interfaces
from buildbot.process.base import BuildRequest
from buildbot.sourcestamp import SourceStamp
from buildbot.process.properties import Properties
from buildbot.test.runutils import SlaveCommandTestBase, RunMixin
from shutil import copytree
import pdb

from django.conf import settings

if not settings.configured:
    settings.configure(DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3'}},
                       INSTALLED_APPS = ('life',
                                         'mbdb',
                                         'l10nstats',
                                         'tinder',
                                         ),
                       BUILDMASTER_BASE = 'basedir')

from l10nstats.models import Run, Tree, Locale, ModuleCount
from django.db import connection

def createStage(basedir, *files):
    '''Create a staging environment in the given basedir

    Each argument is a tuple of
    - a tuple with path segments
    - the content of the file to create
    '''
    for pathsteps, content in files:
        try:
            os.makedirs(os.path.join(basedir, *pathsteps[:-1]))
        except OSError, e:
            if e.errno != 17:
                raise e
        f = open(os.path.join(basedir, *pathsteps), 'w')
        f.write(content)
        f.close()


class SlaveMixin(SlaveCommandTestBase):
    def setUp(self):
        self.setUpBuilder(self.basedir)
        createStage(self.basedir, *self.stageFiles)
        #self._db = connection.creation.create_test_db()

    def tearDown(self):
        #connection.creation.destroy_test_db(self.old_name)
        pass

    def _check(self, res, expectedRC, expectedDetails, exSummary, exStats={}):
        self.assertEqual(self.findRC(), expectedRC)
        res = self._getResults()
        details = res['details']
        summary = res['summary']
        stats = res['stats']
        if expectedDetails is not None:
            self.assertEquals(details, dict())
        for k, v in exSummary.iteritems():
            self.assertEquals(summary[k], v)
        self.assertEquals(stats, exStats)
        return

    def _getResults(self):
        rv = {'stats':{}}
        for d in self.builder.updates:
            if 'result' in d:
                rv.update(d['result'])
            if 'stats' in d:
                rv['stats'] = d['stats']
        return rv


class SlaveSide(SlaveMixin, unittest.TestCase):
    #old_name = settings.DATABASE_NAME
    basedir = "test_compare.testSuccess"
    stageFiles = ((('mozilla', 'app', 'locales', 'l10n.ini'),
                     '''[general]
depth = ../..
all = app/locales/all-locales

[compare]
dirs = app
'''),
    (('mozilla', 'app', 'locales', 'all-locales'),
     '''good
obsolete
missing
'''),
                  (('mozilla','app','locales','en-US','dir','file.dtd'),
                   '<!ENTITY test "value">\n<!ENTITY test2 "value2">\n<!ENTITY test3 "value3">\n'),
                  (('mozilla','embedding','android','locales','l10n.ini'),
                   """[general]
depth = ../../..

[compare]
dirs = embedding/android
"""),
                  (('mozilla','embedding','android','locales','en-US','dir','file.dtd'),
                   '''
<!ENTITY test "value">
<!ENTITY test2 "value2">
<!ENTITY test3 "value3">
<!ENTITY test4 "value4">
<!ENTITY test5 "value5">
'''),
                  (('l10n','good','app','dir','file.dtd'),
                   '''
<!ENTITY test "local value">
<!ENTITY test2 "local value2">
<!ENTITY test3 "local value3">
'''),
                  (('l10n','obsolete','app','dir','file.dtd'),
                   '''
<!ENTITY test "local value">
<!ENTITY test2 "local value 2">
<!ENTITY test3 "local value 3">
<!ENTITY test4 "local value 4">
'''),
                  (('l10n','missing','app','dir','file.dtd'),
                   '<!ENTITY test "local value">\n<!ENTITY test3 "value3">\n'),
                  (('l10n','errors','app','dir','file.dtd'),
                   '''
<!ENTITY test "local " value">
<!ENTITY test2 "local & value2">
<!ENTITY test3 "local <foo> value3">
'''),
                  (('l10n','warnings','app','dir','file.dtd'),
                   u'''
<!ENTITY test "local value">
<!ENTITY test2 "local value2">
<!ENTITY test3 "local &ƞǿŧ; value3">
'''.encode('utf-8')),
                  (('l10n','mixed','app','dir','file.dtd'),
                   '''
<!ENTITY test "local " value">
<!ENTITY test2 "local value2">
<!ENTITY test3 "local &foo; value3">
<!ENTITY test4 "obs1">
'''),
                  (('l10n','android','embedding','android','dir','file.dtd'),
                   '''
<!ENTITY test "local value">
<!ENTITY test2 "local\' value2">
<!ENTITY test3 \'"local\&apos; value3"\'>
<!ENTITY test4 \'"local&apos; value4"\'>
<!ENTITY test5 "value5">
''')
                  )

    def args(self, app, locale, gather_stats=False, initial_module=None):
        return {'workdir': '.',
                'basedir': 'mozilla',
                'inipath': 'mozilla/%s/locales/l10n.ini' % app,
                'l10nbase': 'l10n',
                'locale': locale,
                'tree': app,
                'gather_stats': gather_stats,
                'initial_module': initial_module,
                }

    def testGood(self):
        args = self.args('app', 'good')
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      0,
                      dict(),
                      dict(completion=100))
        return d

    def testGoodStats(self):
        args = self.args('app', 'good', gather_stats=True)
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      0,
                      dict(),
                      dict(completion=100))
        return d

    def testObsolete(self):
        args = self.args('app', 'obsolete')
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      1,
                      None,
                      dict(completion=100))
        return d

    def testMissing(self):
        args = self.args('app', 'missing')
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      2,
                      None,
                      dict(completion=33))
        return d

    def testErrors(self):
        args = self.args('app', 'errors')
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      2,
                      None,
                      dict(errors=3, missing=1))
        return d

    def testWarnings(self):
        args = self.args('app', 'warnings')
        d = self.startCommand(InspectCommand, args)
        d.addCallback(self._check,
                      0,
                      None,
                      dict(warnings=1, completion=100, total=3))
        return d


class SlaveSideDirectory(SlaveMixin, unittest.TestCase):
    #old_name = settings.DATABASE_NAME
    basedir = "test_compare.testSuccess"
    stageFiles = ((('dir', 'good', 'app', 'file.properties'),
        '''
entry = localized value
monty = locother value
'''.encode('utf-8')),
        (('dir', 'en-US', 'app', 'file.properties'),
        '''
entry = English value
monty = Another English value
'''.encode('utf-8')))

    def args(self, locale, gather_stats=False, initial_module=None):
        return {'workdir': 'dir',
                'refpath': 'en-US',
                'l10npath': locale,
                'locale': locale,
                'tree': 'dir-compare',
                'gather_stats': gather_stats
                }

    def testGood(self):
        args = self.args('good')
        d = self.startCommand(InspectDirsCommand, args)
        d.addCallback(self._check,
                      0,
                      dict(),
                      dict(completion=100))
        return d


config = """
from buildbot.process import factory
from l10ninsp.steps import InspectLocale
from buildbot.buildslave import BuildSlave
from buildbot.process.properties import WithProperties

f = factory.BuildFactory()
f.addStep(InspectLocale, master='test-master', workdir='.', basedir='mozilla',
                         inipath='mozilla/app/locales/l10n.ini',
                         l10nbase='l10n', locale=WithProperties('%(locale)s'),
                         tree='app',  gather_stats=True)
af = factory.BuildFactory()
af.addStep(InspectLocale, master='test-master', workdir='../test_builder', basedir='mozilla',
                         inipath='mozilla/embedding/android/locales/l10n.ini',
                         l10nbase='l10n', locale=WithProperties('%(locale)s'),
                         tree='android_app',  gather_stats=True)
BuildmasterConfig = c = {}
c['properties'] = {
  'revisions': [],
  'l10n_branch': 'l10n'
  }
c['slaves'] = [BuildSlave('bot1', 'sekrit')]
c['schedulers'] = []
c['builders'] = []
c['builders'].append({'name': 'test_builder', 'slavename': 'bot1',
                      'factory': f})
c['builders'].append({'name': 'test_android_builder', 'slavename': 'bot1',
                      'factory': af})
c['slavePortnum'] = 0

from bb2mbdb.status import setupBridge
setupBridge('test-master', None, c)
"""

class MasterSide(RunMixin, unittest.TestCase):
    old_name = settings.DATABASE_NAME

    def setUp(self):
        self._db = connection.creation.create_test_db()
        return RunMixin.setUp(self)

    def tearDown(self):
        connection.creation.destroy_test_db(self.old_name)
        return RunMixin.tearDown(self)

    # overloaded to start builds with properties
    def requestBuild(self, builder, locale):
        # returns a Deferred that fires with an IBuildStatus object when the
        # build is finished
        props = Properties()
        props.setProperty('locale', locale, 'scheduler')
        props.setProperty('tree', 'app', 'scheduler')
        req = BuildRequest("forced build", SourceStamp(), builder,
                           properties=props)
        self.control.getBuilder(builder).requestBuild(req)
        return req.waitUntilFinished()

    def testMissing(self):
        return self._testBuild('missing', self._doneMissing)

    def _doneMissing(self, res):
        self.assertEquals(Run.objects.count(), 1, "one run expected")
        r = Run.objects.all()[0]
        self.assertEquals(r.missing, 1)
        self.assertEquals(r.changed, 1)
        self.assertEquals(ModuleCount.objects.count(), 1,
                          "one module expected")
        mc = ModuleCount.objects.all()[0]
        self.assertEquals(mc.name, 'app')
        self.assertEquals(mc.count, 2)
        pass

    def testWarnings(self):
        return self._testBuild('warnings', self._doneWarnings)

    def _doneWarnings(self, res):
        self.assertEquals(Run.objects.count(), 1, "one run expected")
        r = Run.objects.all()[0]
        self.assertEquals(r.missing, 0)
        self.assertEquals(r.changed, 3)
        self.assertEquals(r.warnings, 1)
        self.assertEquals(ModuleCount.objects.count(), 0,
                          "no module expected")
        pass

    def testErrors(self):
        return self._testBuild('errors', self._doneErrors)

    def _doneErrors(self, res):
        self.assertEquals(Run.objects.count(), 1, "one run expected")
        r = Run.objects.all()[0]
        self.assertEquals(r.missing, 1)
        self.assertEquals(r.changed, 2)
        self.assertEquals(r.warnings, 0)
        self.assertEquals(r.errors, 3)
        self.assertEquals(ModuleCount.objects.count(), 1,
                          "no module expected")
        mc = ModuleCount.objects.all()[0]
        self.assertEquals(mc.name, 'app')
        self.assertEquals(mc.count, 1)
        pass


    def testAndroid(self):
        return self._testBuild('android', self._doneAndroid, "test_android_builder")

    def _doneAndroid(self, res):
        self.assertEquals(Run.objects.count(), 1, "one run expected")
        r = Run.objects.all()[0]
        self.assertEquals(r.missing, 0)
        self.assertEquals(r.changed, 4)
        self.assertEquals(r.warnings, 0)
        self.assertEquals(r.errors, 1)
        self.assertEquals(ModuleCount.objects.count(), 1,
                          "no module expected")
        mc = ModuleCount.objects.all()[0]
        self.assertEquals(mc.name, 'embedding/android')
        self.assertEquals(mc.count, 1)
        pass


    def runAll(self):
        '''Run all locales in one go and dump the fixture,
        good for other tests.
        '''
        d = defer.Deferred()
        def dumpFixture(res):
            import os.path
            from django.core.management.commands.dumpdata import Command
            from django.core.management.base import CommandError
            try:
                (open("allruns.json","w")
                 .write(Command().handle(use_natural_keys=True,
                                         indent=2)))
            except CommandError, e:
                log.msg("You might run in to https://code.djangoproject.com/ticket/16317")
                log.err(e)
            (open("mounts_local.py","w")
             .write("""LOG_MOUNTS = {'test-master': '/Users/axelhecht/src/locale-inspector/_trial_temp/basedir/'}
"""))
            d.callback(res)
        def runAndroid(res):
            return self._doBuild(None, 'android', dumpFixture, buildername='test_android_builder')
        def runMixed(res):
            return self._doBuild(None, 'mixed', runAndroid)
        def runWarnings(res):
            return self._doBuild(None, 'warnings', runMixed)
        def runErrors(res):
            return self._doBuild(None, 'errors', runWarnings)
        def runMissing(res):
            return self._doBuild(None, 'missing', runErrors)
        def runObsolete(res):
            return self._doBuild(None, 'obsolete', runMissing)
        self._testBuild('good', runObsolete)
        return d

    def _testBuild(self, locale, cb, buildername="test_builder"):
        m = self.master
        s = m.getStatus()
        m.loadConfig(config)
        m.readConfig = True
        m.startService()
        d = self.connectSlave(builders=["test_builder", "test_android_builder"])
        d.addCallback(self._doBuild, locale, cb, buildername)
        createStage('slavebase-bot1/test_builder', *SlaveSide.stageFiles)
        return d

    def _doBuild(self, res, locale, cb, buildername="test_builder"):
        c = interfaces.IControl(self.master)
        d = self.requestBuild(buildername, locale)
        d2 = self.master.botmaster.waitUntilBuilderIdle(buildername)
        dl = defer.DeferredList([d, d2])
        dl.addCallback(cb)
        return dl
