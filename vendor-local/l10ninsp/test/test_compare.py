# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# test step.ShellCommand and the slave-side commands.ShellCommand

import sys, time, os
from twisted.trial import unittest
from twisted.internet import reactor, defer
from twisted.python import util, log
from l10ninsp.slave import InspectCommand
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

    def _check(self, res, expectedRC, expectedDetails, exSummary):
        self.assertEqual(self.findRC(), expectedRC)
        res = self._getResults()
        details = res['details']
        summary = res['summary']
        if expectedDetails is not None:
            self.assertEquals(details, dict())
        for k, v in exSummary.iteritems():
            self.assertEquals(summary[k], v)
        return

    def _getResults(self):
        rv = {}
        for d in self.builder.updates:
            if 'result' in d:
                rv.update(d['result'])
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

    def args(self, app, locale):
        return {'workdir': '.',
                'basedir': 'mozilla',
                'inipath': 'mozilla/%s/locales/l10n.ini' % app,
                'l10nbase': 'l10n',
                'locale': locale,
                'tree': app,
                }

    def testGood(self):
        args = self.args('app', 'good')
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
