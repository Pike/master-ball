# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from buildbot.process import factory
from buildbot.steps.shell import ShellCommand, SetProperty
from buildbot.process.properties import WithProperties

from twisted.python import log, failure

import l10ninsp.steps
reload(l10ninsp.steps)
from steps import InspectLocale, InspectLocaleDirs, GetRevisions


class Factory(factory.BuildFactory):
    useProgress = False
    
    def __init__(self, basedir, mastername, steps=None):
        factory.BuildFactory.__init__(self, steps)
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
        revs.remove('l10n')
        tree = request.properties.getProperty('tree')
        sourceSteps = tuple(
            (ShellCommand, {'command': 
                            ['hg', 'update', '-C', '-r', 
                             WithProperties('%%(%s_revision)s' % mod)],
                            'workdir': WithProperties(self.base + 
                                                      '/%%(%s_branch)s' % mod),
                            'haltOnFailure': True})
            for mod in revs)
        l10nSteps = (
            (ShellCommand, {'command': 
                            ['hg', 'update', '-C', '-r', 
                             WithProperties('%(l10n_revision)s')],
                            'workdir': WithProperties(self.base + 
                                                      '/%(l10n_branch)s/%(locale)s'),
                            'haltOnFailure': True}),
            )
        inspectSteps = (
            (InspectLocale, {
                    'master': self.mastername,
                    'workdir': self.base,
                    'basedir': WithProperties('%(en_branch)s'),
                    'inipath': WithProperties('%(en_branch)s/%(l10n.ini)s'),
                    'l10nbase': WithProperties('%(l10n_branch)s'),
                    'locale': WithProperties('%(locale)s'),
                    'tree': tree,
                    'gather_stats': True,
                    }),)
        return sourceSteps + l10nSteps + inspectSteps


class DirFactory(Factory):
    """Factory used for projects like weave.
    """
    def createSteps(self, request):
        revs = ['en', 'l10n']
        request.properties.update({'revisions': revs}, 'Factory')
        tree = request.properties.getProperty('tree')
        preSteps = ((GetRevisions, {}),)
        sourceSteps = (
            (ShellCommand, {'command': 
                            ['hg', 'update', '-C', '-r', 
                             WithProperties('%(en_revision)s')],
                            'workdir': WithProperties(self.base + 
                                                      '/%(en_branch)s'),
                            'haltOnFailure': True}),
            (ShellCommand, {'command': 
                            ['hg', 'update', '-C', '-r', 
                             WithProperties('%(l10n_revision)s')],
                            'workdir': WithProperties(self.base + 
                                                      '/%(l10n_branch)s/%(locale)s'),
                            'haltOnFailure': True}),
            (SetProperty, {'command': 
                           ['hg', '-R', '.', 'id', '--id', '--rev', '.'], 
                            'workdir': WithProperties(self.base + 
                                                      '/%(en_branch)s'),
                           'haltOnFailure': True,
                           'property': 'en_revision' }),
            (SetProperty, {'command': 
                           ['hg', '-R', '.', 'id', '--id', '--rev', '.'], 
                            'workdir': WithProperties(self.base + 
                                                      '/%(l10n_branch)s/%(locale)s'),
                           'haltOnFailure': True,
                           'property': 'l10n_revision' }),
            )
        inspectSteps = (
            (InspectLocaleDirs, {
                    'master': self.mastername,
                    'workdir': self.base,
                    'basedir': WithProperties('%(en_branch)s'),
                    'refpath': WithProperties('%(refpath)s'),
                    'l10npath': WithProperties('%(l10npath)s'),
                    'locale': WithProperties('%(locale)s'),
                    'tree': tree,
                    'gather_stats': True,
                    }),)
        return preSteps + sourceSteps + inspectSteps
