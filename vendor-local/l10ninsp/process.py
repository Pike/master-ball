# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from buildbot.process import factory
from buildbot.steps.shell import ShellCommand
from buildbot.process.properties import WithProperties

from twisted.python import log

from l10ninsp.steps import InspectLocale


class Factory(factory.BuildFactory):
    useProgress = False

    def __init__(self, basedir, mastername, steps=None, hg_shares=None):
        factory.BuildFactory.__init__(self, steps)
        self.hg_shares = hg_shares
        self.base = basedir
        self.mastername = mastername

    def newBuild(self, requests):
        steps = self.createSteps(requests[-1])
        b = self.buildClass(requests)
        b.useProgress = self.useProgress
        b.setStepFactories(steps)
        return b

    def createSteps(self, request):
        revs = request.properties.getProperty('revisions')
        if revs is None:
            revs = ['en', 'l10n']
            log.msg('no revisions given in ' + str(request.properties))
        else:
            revs = revs[:]
        tree = request.properties.getProperty('tree')
        hg_workdir = self.base
        shareSteps = tuple()
        hg = ['hg']
        if self.hg_shares is not None:
            hg_workdir = self.hg_shares
            hg += ['--config', 'extensions.share=']
            shareSteps = tuple(
                (ShellCommand, {
                    'command': [
                        'mkdir', '-p', WithProperties('%%(%s_branch)s' % mod)],
                    'workdir': hg_workdir
                })
                for mod in revs) + tuple(
                (ShellCommand, {
                    'command': hg + [
                        'share', '-U',
                        WithProperties(self.base + '/%%(%s_branch)s' % mod),
                        WithProperties('%%(%s_branch)s' % mod)],
                    'workdir': hg_workdir,
                    'flunkOnFailure': False
                })
                for mod in revs)
        sourceSteps = tuple(
            (ShellCommand, {'command':
                            hg + ['update', '-C', '-r',
                                  WithProperties('%%(%s_revision)s' % mod)],
                            'workdir': WithProperties(hg_workdir +
                                                      '/%%(%s_branch)s' % mod),
                            'haltOnFailure': True})
            for mod in revs)
        redirects = {}
        for key, value, src in request.properties.asList():
            if key.startswith('local_'):
                redirects[key[len('local_'):]] = value
        inspectSteps = (
            (InspectLocale, {
                    'master': self.mastername,
                    'workdir': hg_workdir,
                    'inipath': WithProperties('%(inipath)s'),
                    'l10nbase': WithProperties('%(l10nbase)s'),
                    'redirects': redirects,
                    'locale': WithProperties('%(locale)s'),
                    'tree': tree,
                    }),)
        return shareSteps + sourceSteps + inspectSteps
