# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

from buildbot.status.base import StatusReceiverMultiService, StatusReceiver
from twisted.python import log

import markus


metrics = markus.get_metrics('elmo-builds')


class MarkusStatusReceiver(StatusReceiverMultiService):
    '''StatusReceiver for markus metrics.
    '''

    def logPending(self):
        status = self.parent.getStatus()
        pending = current = 0
        for buildername in status.getBuilderNames():
            builder = status.getBuilder(buildername)
            pending += len(builder.getPendingBuilds())
            current += len(builder.getCurrentBuilds())
        metrics.gauge('pending_builds', pending)
        metrics.gauge('current_builds', current)

    def setServiceParent(self, parent):
        StatusReceiverMultiService.setServiceParent(self, parent)
        self.setup()

    def setup(self):
        log.msg("markus subscribing")
        status = self.parent.getStatus()
        status.subscribe(self)

    def builderAdded(self, builderName, builder):
        log.msg("adding %s to markus" % builderName)
        return self

    def requestSubmitted(self, request):
        self.logPending()
        submitTimestamp = request.getSubmitTime()
        def addBuild(build):
            log.msg("adding build to markus")
            pass
        request.subscribe(addBuild)

    def builderChangedState(self, builderName, state):
        log.msg("%s changed state to %s" % (builderName, state))

    def buildStarted(self, builderName, build):
        self.logPending()
        log.msg("build started on  %s" % builderName)

    def buildFinished(self, builderName, build, results):
        start_time, end_time = build.getTimes()
        metrics.timing('buildtime', value=(end_time-start_time)*1000, tags=[builderName])
        changes = build.getChanges()
        src_times = filter(None, (c.getTimes()[0] for c in changes))
        if src_times:
            metrics.timing('end_to_end_time', (end_time - min(src_times))*1000, tags=[builderName])
        self.logPending()
        log.msg("finished build on %s with %s" %
                (builderName, str(results)))

    def builderRemoved(self, builderName):
        log.msg("removing %s from markus" % builderName)
        # nothing to do here, afaict.
        pass
