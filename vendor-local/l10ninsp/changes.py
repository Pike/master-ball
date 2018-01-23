# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from calendar import timegm

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.task import LoopingCall

from buildbot.status.builder import EXCEPTION
from buildbot.changes import base, changes


def createChangeSource(pollInterval=3*60):
    from life.models import Push, Branch, File
    from django.db import transaction

    class MBDBChangeSource(base.ChangeSource):
        debug = True

        def __init__(self,  latest_push, pollInterval=30, branch='default'):
            self.pollInterval = pollInterval
            self.latest = latest_push
            self.branch, created = \
                Branch.objects.get_or_create(name=branch)

        def startService(self):
            self.loop = LoopingCall(self.poll)
            base.ChangeSource.startService(self)
            reactor.callLater(0, self.loop.start, self.pollInterval)

        def stopService(self):
            self.loop.stop()
            return base.ChangeSource.stopService(self)

        def poll(self):
            '''Check for new pushes.
            '''
            import django.db.utils
            try:
                with transaction.atomic():
                    new_pushes = (
                        Push.objects
                        .filter(pk__gt=self.latest)
                        .order_by('pk'))
                    if self.debug:
                        log.msg('mbdb changesource found %d pushes after %d' %
                                (new_pushes.count(), self.latest))
                    push = None
                    for push in new_pushes:
                        self.submitChangesForPush(push)
                    if push is not None:
                        self.latest = push.id
            except django.db.utils.OperationalError:
                from django import db
                db.connection.close()
                log.msg('Django database OperationalError caught')

        def submitChangesForPush(self, push):
            if self.debug:
                log.msg('submitChangesForPush called')
            repo = push.repository
            if repo.forest is not None:
                branch = repo.forest.name.encode('utf-8')
                locale = repo.name[len(branch) + 1:].encode('utf-8')
            else:
                branch = repo.name.encode('utf-8')
            files = [f.encode('utf-8') for f in
                     File.objects
                         .filter(changeset__pushes=push)
                         .distinct()
                         .values_list('path', flat=True)]
            when = timegm(push.push_date.utctimetuple()) + \
                push.push_date.microsecond/1000.0/1000
            c = changes.Change(who=push.user.encode('utf-8'),
                               files=files,
                               revision=push.tip.revision.encode('utf-8'),
                               comments=push.tip.description.encode('utf-8'),
                               when=when,
                               branch=branch)
            if repo.forest is not None:
                # locale change
                c.locale = locale
            self.parent.addChange(c)

        def replay(self, builder,
                   startPush=None, startTime=None, endTime=None):
            bm = self.parent.parent.botmaster
            qd = {}
            if startTime is not None:
                qd['push_date__gte'] = startTime
            if endTime is not None:
                qd['push_date__lte'] = endTime
            if startPush is not None:
                qd['id__gte'] = startPush
            q = Push.objects.filter(**qd).order_by('push_date')
            i = q.iterator()
            if self.debug:
                log.msg('replay called for %d pushes' % q.count())

            def next(_cb):
                try:
                    p = i.next()
                except StopIteration:
                    log.msg("done iterating")
                    return
                self.submitChangesForPush(p)

                def stumble():
                    bm.waitUntilBuilderIdle(builder).addCallback(_cb, _cb)
                reactor.callLater(.5, stumble)

            def cb(res, _cb):
                reactor.callLater(.5, next, _cb)
            next(cb)

        def describe(self):
            return str(self)

        def __str__(self):
            return "MBDBChangeSource"

    latest_push = get_last_push_and_clean_up()
    c = MBDBChangeSource(latest_push, pollInterval)
    return c


def get_last_push_and_clean_up():
    '''Find the starting point for the push changesource.

    This sets the changesource such that missed pushes since the last shut
    down get retriggered.
    Also, if the master didn't shut down cleanly, re-schedule the affected
    changes, and clean up the mbdb.
    '''
    from life.models import Changeset, Push
    from mbdb.models import Build, BuildRequest, Change
    from django.db.models import F, Max, Min, Q
    # Check for debris of a bad shut-down
    # Indications:
    # - Pending builds (build requests w/out builds, but with changes)
    # - Unfinished builds (no endtime)
    #
    # Find all revisions, find the latest push for each,
    # find the earliest of those pushes.
    revs = []
    pending_requests = (
        BuildRequest.objects
        .filter(
            builds__isnull=True,
            sourcestamp__changes__isnull=False
        )
    )
    pending_query = Q(stamps__requests__in=pending_requests)
    unfinished_builds = (
        Build.objects
        .filter(endtime__isnull=True)
    )
    unfinished_query = Q(stamps__builds__in=unfinished_builds)
    revs.extend(
        Change.objects
        .filter(
            pending_query | unfinished_query
        )
        .filter(revision__isnull=False)
        .values_list('revision', flat=True)
        .distinct()
    )
    if revs:
        # clean up
        # remove pending build requests
        pending_requests.delete()
        # set end time on builds to last step endtime or starttime
        # result of build and last step to EXCEPTION
        for build in unfinished_builds:
            (
                build.steps
                .filter(endtime__isnull=True)
                .update(endtime=F('starttime'), result=EXCEPTION)
            )
            build.endtime = max(
                list(build.steps.values_list('endtime', flat=True)) +
                [build.starttime]
            )
            build.result = EXCEPTION
            build.save()
        # now that we cleaned up the debris, let's see where we want to start
        changesets = (
            Changeset.objects
            .filter(revision__in=revs)
            .annotate(last_push=Max('pushes'))
        )
        last_push = changesets.aggregate(Min('last_push'))['last_push__min']
        if last_push is not None:
            # let's redo starting from that push, so return that - 1
            log.msg(
                "replaying revisions: %s, %d changesets, first push: %d" %
                (", ".join(revs), changesets.count(), last_push)
            )
            return last_push - 1

    # OK, so either there wasn't any debris, or there was no push on it
    # Find the last push with a run, in id ordering, not push_date ordering.
    for p in Push.objects.order_by('-pk').prefetch_related('changesets')[:100]:
        if p.tip.run_set.exists():
            log.msg("restarting after a push with run: %d" % p.id)
            return p.id

    # We don't have recent builds, just use the last push
    try:
        p = Push.objects.order_by('-pk')[0]
        log.msg("restarting after the last push: %d" % p.id)
        return p.id
    except IndexError:
        # new data
        log.msg("new data, starting poller with 0")
        return 0
