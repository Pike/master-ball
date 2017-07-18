# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from twisted.internet import reactor, defer
from twisted.python import log
from twisted.python.failure import Failure

from buildbot.slave.registry import registerSlaveCommand
from buildbot.slave.commands import Command
from buildbot.status.builder import SUCCESS, WARNINGS, FAILURE, EXCEPTION

import codecs
import json
import os
from compare_locales.paths import EnumerateSourceTreeApp
from compare_locales.compare import compareProjects
from django.conf import settings
from django.db import connection
import elasticsearch

from l10nstats.models import Run, Build
from life.models import Tree, Locale, Changeset


class InspectCommand(Command):
    """
    Do CompareLocales on the slave.

    To be able to run this, you have to

        import l10ninsp.slave

    from the slave's buildbot.tac
    """

    # debug = True

    def setup(self, args):
        self.args = args.copy()

    def start(self):
        if self.debug:
            log.msg('Compare started')

        d = defer.Deferred()
        connection.close_if_unusable_or_obsolete()
        d.addCallback(self.doCompare)
        reactor.callLater(0, d.callback, None)
        d.addBoth(self.finished)
        return d

    def doCompare(self, *args):
        locale, workdir = (self.args[k] for k in ('locale', 'workdir'))
        log.msg('Starting to compare %s in %s' % (locale, workdir))
        log.msg(str(self.args))
        self.sendStatus({'header': 'Comparing %s against en-US for %s\n'
                         % (locale, workdir)})
        try:
            loc = Locale.objects.get(code=self.args['locale'])
            build = Build.objects.get(id=self.args['build'])
        except Exception, e:
            log.msg(e)
            self.rc = EXCEPTION
            return
        revs = []
        for rev in self.args['revs']:
            cs = None
            try:
                cs = Changeset.objects.get(revision__startswith=rev[:12])
                revs.append(cs)
            except (Changeset.DoesNotExist, Changeset.MultipleObjectsReturned):
                log.msg("no changeset found for %s" % rev)
        workingdir = os.path.join(self.builder.basedir, workdir)
        try:
            observers = self._compare(workingdir, locale, args)
        except Exception, e:
            log.msg('%s comparison failed with %s' % (locale, str(e)))
            log.msg(Failure().getTraceback())
            self.rc = EXCEPTION
            return
        self.rc = SUCCESS
        tree = Tree.objects.get(code=self.args['tree'])
        for observer in observers:
            try:
                self.report_compare_locales(build, revs, loc, tree, observer)
            except Exception, e:
                log.msg(e)
                self.rc = EXCEPTION
            if self.rc == EXCEPTION:
                return

    def report_compare_locales(self, build, revs, loc, tree, observer):
        '''Add the results of compare-locales for a particular tree
        to the elmo data, creating a Run, and associating that with
        the given build and revisions.
        Adding the details to ES.
        '''
        summary = observer.summary[loc.code]
        if summary.get('obsolete', 0) > 0:
            self.rc = WARNINGS
        if (summary.get('missing', 0) +
                summary.get('missingInFiles', 0) +
                summary.get('errors', 0) > 0):
            self.rc = FAILURE
        total = sum(summary[k] for k in ['changed', 'unchanged', 'missing',
                                         'missingInFiles'])
        summary['completion'] = int((summary['changed'] * 100) / total)
        summary['total'] = total

        runargs = {
            'locale': loc,
            'tree': tree,
            'build': build,
            'srctime': self.args['srctime']}
        for k in ('missing', 'missingInFiles', 'obsolete', 'total',
                  'changed', 'unchanged', 'keys', 'completion', 'errors',
                  'report', 'warnings'):
            runargs[k] = summary.get(k, 0)
        try:
            dbrun = Run.objects.create(**runargs)
        except Exception, e:
            log.msg(e)
            self.rc = EXCEPTION
            return
        dbrun.revisions = revs
        dbrun.save()
        dbrun.activate()
        try:
            self.sendStatus({
                'stdout': codecs.utf_8_encode(observer.serialize())[0]})
        except Exception, e:
            log.msg('%s status sending failed with %s' % (loc.code, str(e)))
            self.rc = EXCEPTION
            return
        es = elasticsearch.Elasticsearch(hosts=settings.ES_COMPARE_HOST)
        # create our ES document to index in ES
        body = {
            'run': dbrun.id,
            'details': observer.details.toJSON()
        }
        try:
            rv = es.index(index=settings.ES_COMPARE_INDEX, body=body,
                          doc_type='comparison', id=dbrun.id)
        except Exception, e:
            log.msg(e)
            self.rc = EXCEPTION
            return
        log.msg('es.index: ' + json.dumps(rv))

    def _compare(self, workingdir, locale, args):
        inipath, l10nbase, redirects = (
            self.args[k]
            for k in ('inipath', 'l10nbase', 'redirects'))
        try:
            app = EnumerateSourceTreeApp(os.path.join(workingdir, inipath),
                                         workingdir,
                                         os.path.join(workingdir, l10nbase),
                                         redirects,
                                         [locale])
            observers = compareProjects(
                [app.asConfig()],
                file_stats=True)
        except Exception as e:
            log.msg(e)
            raise
        return observers

    def finished(self, *args):
        # sometimes self.rc isn't set here, no idea why
        try:
            rc = self.rc
        except AttributeError:
            rc = FAILURE
        self.sendStatus({'rc': rc})


registerSlaveCommand('moz_inspectlocales', InspectCommand, '0.2')
