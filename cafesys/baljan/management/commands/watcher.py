# -*- coding: utf-8 -*-
from subprocess import call
from subprocess import Popen
from time import sleep

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command

import pyinotify

class OnWriteHandler(pyinotify.ProcessEvent):

    def my_init(self, cwd, extension, cmd):
        self.cwd = cwd
        self.extensions = extension.split(',')
        self.cmd = cmd

    def _run_cmd(self):
        print '==> Modification detected'
        call(self.cmd.split(' '), cwd=self.cwd)

    def process_IN_MODIFY(self, event):
        if all(not event.pathname.endswith(ext) for ext in self.extensions):
            return
        self._run_cmd()

class Command(BaseCommand):

    def tear_down(self):
        if hasattr(self, 'procs'):
            [p.kill() for p in self.procs.values()]

    def handle(self, **options):
        self.procs = {}
        try:
            self.procs['sass'] = Popen([
                'sass',
                '--load-path',
                'baljan/static/sass-twitter-bootstrap/lib',
                '--watch',
                'baljan/static/sass:baljan/static/css',
                '--trace',
            ])

            self.procs['coffee'] = Popen([
                'coffee',
                '-wbo',
                'baljan/static/js',
                'baljan/static/coffee',
            ])

            wm = pyinotify.WatchManager()
            handler = OnWriteHandler(
                cwd=settings.PROJECT_ROOT, 
                extension='css,js',
                cmd='jammit',
            )
            notifier = pyinotify.Notifier(wm, default_proc_fun=handler)
            wm.add_watch('baljan/static', pyinotify.ALL_EVENTS, rec=True, auto_add=True)
            notifier.loop()
        except KeyboardInterrupt, e:
            self.tear_down()
            return
        except Exception, e:
            self.tear_down()
            raise e

