# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from twisted.python import log
from buildbot.process.buildstep import (
    BuildStep, LoggingBuildStep, LoggedRemoteCommand)
from buildbot.status.builder import SUCCESS, FAILURE
from buildbot.process.properties import WithProperties

from ConfigParser import ConfigParser, NoSectionError, NoOptionError
from cStringIO import StringIO
import urllib2

from mbdb.models import Build

import logger
import util


class InspectLocale(LoggingBuildStep):
    """
    This class hooks up CompareLocales in the build master.
    """

    name = "moz_inspectlocales"
    cmd_name = name

    description = ["comparing"]
    descriptionDone = ["compare", "locales"]

    def __init__(self, master, workdir, inipath, l10nbase, redirects,
                 locale, tree,
                 **kwargs):
        """
        @type  master: string
        @param master: name of the master

        @type  workdir: string
        @param workdir: local directory (relative to the Builder's root)
                        where the mozilla and the l10n trees reside

        @type inipath: string
        @param inipath: path to the l10n.ini file, relative to the workdir

        @type l10nbase: string
        @param l10nbase: path to the localization dirs, relative to the workdir

        @type  locale: string
        @param locale: Language code of the localization to be compared.

        @type  tree: string
        @param tree: The tree identifier for this branch/product combo.
        """

        LoggingBuildStep.__init__(self, **kwargs)

        self.args = {'workdir': workdir,
                     'inipath': inipath,
                     'l10nbase': l10nbase,
                     'redirects': redirects,
                     'locale': locale,
                     'tree': tree}
        self.master = master

    def describe(self, done=False):
        if done:
            return self.descriptionDone
        return self.description

    def start(self):
        log.msg('starting with compare')
        args = {}
        args.update(self.args)
        for k, v in args.iteritems():
            if isinstance(v, WithProperties):
                args[k] = self.build.getProperties().render(v)
        try:
            args['tree'] = self.build.getProperty('tree')
        except KeyError:
            pass
        buildername = self.build.getProperty('buildername')
        buildnumber = self.build.getProperty('buildnumber')
        args['srctime'] = self.build.getProperty('srctime')
        try:
            build = Build.objects.get(builder__master__name=self.master,
                                      builder__name=buildername,
                                      buildnumber=buildnumber)
            args['build'] = build.id
        except Build.DoesNotExist:
            args['build'] = None
        args['revs'] = []
        for rev in self.build.getProperty('revisions'):
            ident = self.build.getProperty('%s_revision' % rev)
            args['revs'].append(ident)

        self.descriptionDone = [args['locale'], args['tree']]
        cmd = LoggedRemoteCommand(self.cmd_name, args)
        self.startCommand(cmd, [])


class TreeLoader(BuildStep):
    '''BuildStep to load data from l10n.ini on remote repos.

    Does mostly just async network traffic, directly on the master,
    it wouldn't be more work there if we'd use the slave, and then
    marshall the data through the network back to the master.
    '''
    def __init__(self, treename, l10nbuilds, cb=None, **kwargs):
        '''Create a TreeLoader step. In addition to the standard arguments,
        treename is the name of the tree,
        l10nbuilds is the local ini file describing the builds,
        cb is a callback with signature (tree, changes=None)
        '''
        BuildStep.__init__(self, **kwargs)
        self.addFactoryArguments(treename=treename,
                                 l10nbuilds=l10nbuilds,
                                 cb=cb)
        self.treename = treename
        self.l10nbuilds = l10nbuilds
        self.cb = cb
        self.timeout = 5
        self.headers = {
            'User-Agent': 'Elmo/1.0 (l10n.mozilla.org)'
        }

    def start(self):
        from scheduler import Tree
        loog = self.addLog('stdio')
        self.pending = 0
        properties = self.build.getProperties()
        self.rendered_tree = tree = properties.render(self.treename)
        l10nbuilds = properties.render(self.l10nbuilds)
        cp = ConfigParser()
        cp.read(l10nbuilds)
        repo = cp.get(tree, 'repo')
        branch = cp.get(tree, 'mozilla')
        path = cp.get(tree, 'l10n.ini')
        l10nbranch = cp.get(tree, 'l10n')
        locales = cp.get(tree, 'locales')
        if locales == 'all':
            alllocales = "yes"
        else:
            alllocales = "no"
            properties.update({'locales': filter(None, locales.split())},
                              "Build")
        self.tree = Tree(self.rendered_tree, repo, branch, l10nbranch, path)
        loog.addStdout('Loading l10n.inis for %s\n' % self.rendered_tree)
        logger.debug('scheduler.l10n.tree',
                     'Loading l10n.inis for %s, alllocales: %s' %
                     (self.rendered_tree, alllocales))
        self.loadIni(repo, branch, path, alllocales)
        self.endLoad()

    def loadIni(self, repo, branch, path, alllocales="no"):
        url = repo + '/' + branch + '/raw-file/default/' + path
        self.getLog('stdio').addStdout('\nloading %s\n' % url)
        self.step_status.setText(['loading', 'l10n.ini'])
        self.step_status.setText2([repo, branch, path])
        self.pending += 1
        request = urllib2.Request(url, headers=self.headers)
        inicontent = urllib2.urlopen(request, timeout=self.timeout).read()
        self.onL10niniLoad(inicontent, repo, branch, path, alllocales)

    def onL10niniLoad(self, inicontent, repo, branch, path, alllocales):
        self.pending -= 1
        logger.debug('scheduler.l10n.tree',
                     'Loaded %s, alllocales: %s' % (path, alllocales))
        self.step_status.setText(['loaded', 'l10n.ini'])
        loog = self.getLog('stdio')
        cp = ConfigParser()
        cp.readfp(StringIO(inicontent), path)
        try:
            dirs = cp.get('compare', 'dirs').split()
        except (NoOptionError, NoSectionError):
            dirs = []
        try:
            dirs += cp.get('extras', 'dirs').split()
        except (NoOptionError, NoSectionError):
            pass
        try:
            tld = cp.get('compare', 'tld')
            # remove tld from comparison dirs
            if tld in dirs:
                dirs.remove(tld)
        except (NoOptionError, NoSectionError):
            tld = None

        if dirs:
            loog.addStdout("adding %s on branch %s for %s\n" %
                           (", ".join(dirs), branch, self.rendered_tree))
        if tld is not None:
            loog.addStdout("adding a tld compare for %s on %s\n" %
                           (tld, branch))

        self.tree.addData(branch, path, dirs, tld)

        try:
            for title, _path in cp.items('includes'):
                try:
                    # check if the load details are overloaded
                    details = dict(cp.items('include_%s' % title))
                    if details['type'] != 'hg':
                        continue
                    loog.addStdout("need to load %s from %s on %s, %s\n" %
                                   (title, details['l10n.ini'],
                                    details['repo'],
                                    details['mozilla']))
                    # check if we got the en-US branch already, if not
                    # we're likely loading toolkit off a different repo
                    enbranch = details['mozilla']
                    if enbranch not in self.tree.branches.values():
                        self.tree.branches[title] = enbranch
                    self.loadIni(details['repo'], details['mozilla'],
                                 details['l10n.ini'])
                except NoSectionError:
                    loog.addStdout("need to load %s from %s\n" %
                                   (title, _path))
                    self.loadIni(repo, branch, _path)
        except NoSectionError:
            pass
        try:
            if alllocales == 'yes':
                allpath = cp.get('general', 'all')
                self.tree.all_locales = allpath
                logger.debug('scheduler.l10n.tree',
                             'loading all-locales for %s from %s' %
                             (self.tree.name, allpath))
                self.pending += 1
                request = urllib2.Request(
                    repo + '/' + branch + '/raw-file/default/' + allpath,
                    headers=self.headers)
                content = urllib2.urlopen(request, timeout=self.timeout).read()
                self.allLocalesLoaded(content)
        except NoSectionError:
            pass

    def onL10niniFail(self, failure):
        self.pending -= 1
        loog = self.getLog('stdio')
        loog.addStderr(failure.getErrorMessage())
        if self.pending <= 0:
            self.step_status.setText(
                ['configure', self.rendered_tree, 'failed'])
            self.step_status.setText2([])
            self.finished(FAILURE)
        return failure

    def allLocalesLoaded(self, page):
        self.pending -= 1
        locales = util.parseLocales(page)
        self.build.setProperty('locales', locales,
                               'Build')
        logger.debug('scheduler.l10n.tree',
                     'all-locales loaded, found %s' %
                     str(locales))

    def allLocalesFailed(self, failure):
        self.pending -= 1
        if self.pending <= 0:
            self.step_status.setText(
                ['configure', self.rendered_tree, 'failed'])
            self.step_status.setText2([])
            self.finished(FAILURE)
        return failure

    def endLoad(self):
        logger.debug('scheduler.l10n.tree',
                     'load ended, pending jobs: %d' % self.pending)
        if self.pending <= 0:
            self.step_status.setText(['configured', self.rendered_tree])
            self.step_status.setText2([])
            if self.cb is not None:
                try:
                    self.tree.locales = (self.build
                                             .getProperties()
                                             .getProperty('locales', [])[:])
                    self.cb(self.tree, changes=self.build.allChanges())
                except Exception, e:
                    logger.debug('scheduler.l10n.tree', str(e))
            self.finished(SUCCESS)
