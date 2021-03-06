from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth.models import User, Group
import MySQLdb
import MySQLdb.cursors
from datetime import date, datetime
from baljan.models import Profile, Semester, ShiftSignup, Shift, BoardPost
from baljan.models import OnCallDuty, Good, Order
from baljan.models import OldCoffeeCard, OldCoffeeCardSet
from baljan.util import get_logger, get_or_create_user
from baljan import pseudogroups
from baljan import orders
from dateutil.relativedelta import relativedelta
import re
from emailconfirmation.models import EmailAddress

log = get_logger('baljan.migration', with_sentry=False)

manual_board = []

class Import(object):
    def __init__(self):
        self._users = {}

        # Make sure that all needed settings and such are configured.
        settingfmt = 'OLD_SYSTEM_MYSQL_%s'
        valid = True
        errs = []
        for setting in (
                'LOGIN',
                'PASSWORD',
                'DB',
                'HOST',
                ):
            full_setting = settingfmt % setting
            if hasattr(settings, full_setting):
                pass
            else:
                valid = False
                errs.append("missing setting %s" % full_setting)
        
        if not valid:
            raise CommandError('Bad configuration: %s' % ', '.join(errs))

        def s(setting):
            return getattr(settings, settingfmt % setting.upper())
        self._db = MySQLdb.connect(
                user=s('login'),
                passwd=s('password'),
                host=s('host'),
                db=s('db'))

        self.enc = 'latin-1'

    def _cursor(self):
        return self._db.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    def _decode(self, s):
        return s.decode(self.enc)

    def get_user_dicts(self, user_id=None):
        c = self._cursor()
        if user_id is None:
            c.execute('''
SELECT user.*, person.* FROM user INNER JOIN person ON person.id=user.id
''')

            fetched = c.fetchall()
            c.close()
            return fetched
        else:
            c.execute('''
SELECT user.*, person.* FROM user INNER JOIN person ON person.id=user.id WHERE person.id=%d
''' % user_id)
            fetched = c.fetchone()
            c.close()
            return fetched

    def _get_phone(self, user_dict):
        c = self._cursor()
        c.execute('''
SELECT nummer FROM telefon WHERE persid=%d
''' % user_dict['id'])
        phone = c.fetchone()
        if phone: # validate
            trial = re.sub("[^0-9]", "", phone['nummer'])[:10]
            phone = None
            if trial.startswith('07'): # only cells
                phone = trial
        return phone

    def setup_users(self):
        user_dicts = self.get_user_dicts()
        decode = self._decode
        created_count, existing_count, skipped = 0, 0, []
        username_pattern = re.compile("^[a-z]{2,5}[0-9]{3,3}$")
        for ud in user_dicts:
            uname = decode(ud['login']).lower()
            if username_pattern.match(uname) is None:
                skipped.append(uname)
                continue

            phone = self._get_phone(ud)
            first_name = decode(ud['fnamn'])
            last_name = decode(ud['enamn'])

            # Do not update the phone or name of an already imported users, we
            # risk overwriting updated credentials.
            user_exists = User.objects.filter(username__exact=uname).count() != 0
            if user_exists:
                phone = None
                first_name = None
                last_name = None

            eaddr_custom = None
            if ud['epost']:
                eaddr_custom = decode(ud['epost'])

            u, created = get_or_create_user(
                username=uname, 
                first_name=first_name,
                last_name=last_name,
                email=eaddr_custom,
                phone=phone,
                show_email=ud['ejepost'] == 0,
                show_profile=ud['dold'] == 0,
            )
            p = u.get_profile()

            if created:
                log.info('created: %r %r' % (u, p))
                created_count += 1
            else:
                log.info('existing: %r %r' % (u, p))
                existing_count += 1

        log.info('%d/%d/%d user(s) created/existing/skipped' % (
            created_count, existing_count, len(skipped)))
        if len(skipped):
            log.warning('skipped: %s' % ", ".join(skipped))

    def get_shift_dicts(self):
        c = self._cursor()
        c.execute('''SELECT * FROM persbok''')
        fetched = c.fetchall()
        return fetched

    def _is_spring(self, day):
        return day.month < 7

    def _sem_for_day(self, day):
        sem = Semester.objects.for_date(day)
        if sem is None: # automatically create semester
            spring = self._is_spring(day)
            if spring:
                name = "VT%s" % day.year
                start = date(day.year, 1, 1)
                end = date(day.year, 7, 1)
            else:
                name = "HT%s" % day.year
                start = date(day.year, 8, 1)
                end = date(day.year, 12, 31)

            sem = Semester(name=name, start=start, end=end)
            try:
                sem.save()
                log.info('created %r' % sem)
            except:
                raise Exception("day=%s (m=%s), start=%s, end=%s" % (day, day.month, sem.start, sem.end))
        return sem

    def setup_shifts(self):
        shift_dicts = self.get_shift_dicts()
        decode = self._decode
        created_count, existing_count, skipped = 0, 0, []
        cleared_shifts = {}
        for sd in shift_dicts:
            day = sd['dag']
            sem = self._sem_for_day(day)

            ud = self.get_user_dicts(user_id=sd['persid'])
            if ud is None:
                skipped.append("user %s" % sd['persid'])
                continue

            uname = decode(ud['login']).lower()

            span = 2 if sd['em'] == 1 else 0


            shift = Shift.objects.get(
                    when=day,
                    span=span,
                    semester=sem)

            if not cleared_shifts.has_key(shift):
                ShiftSignup.objects.filter(shift=shift).delete()
                cleared_shifts[shift] = True

            signup, created = ShiftSignup.objects.get_or_create(
                    shift=shift,
                    user=User.objects.get(username=uname),
                    )

            if created:
                log.info('created: %r' % signup)
                created_count += 1
            else:
                log.info('existing: %r' % signup)
                existing_count += 1

        log.info('%d/%d/%d shift(s) created/existing/skipped' % (
            created_count, existing_count, len(skipped)))
        if len(skipped):
            log.warning('skipped: %s' % ", ".join(skipped))

    def get_oncall_dicts(self):
        c = self._cursor()
        c.execute('''SELECT * FROM jour''')
        return c.fetchall()

    def setup_oncallduties(self):
        oncall_dicts = self.get_oncall_dicts()
        decode = self._decode
        created_count, existing_count, skipped = 0, 0, []
        cleared_shifts = {}
        for oc in oncall_dicts:
            day = oc['dag']
            sem = Semester.objects.for_date(day)
            ud = self.get_user_dicts(user_id=oc['persid'])
            if ud is None:
                skipped.append("user %s" % oc['persid'])
                continue

            uname = decode(ud['login']).lower()
            shift = Shift.objects.get(
                    when=day,
                    span=oc['pass'], # uses the same integers
                    semester=sem)

            if not cleared_shifts.has_key(shift):
                OnCallDuty.objects.filter(shift=shift).delete()
                cleared_shifts[shift] = True

            oncall, created = OnCallDuty.objects.get_or_create(
                    shift=shift,
                    user=User.objects.get(username=uname),
                    )

            if created:
                log.info('created: %r' % oncall)
                created_count += 1
            else:
                log.info('existing: %r' % oncall)
                existing_count += 1

        log.info('%d/%d/%d call duty shift(s) created/existing/skipped' % (
            created_count, existing_count, len(skipped)))
        if len(skipped):
            log.warning('skipped: %s' % ", ".join(skipped))

    def setup_current_workers_and_board(self):
        sem = Semester.objects.for_date(date.today())
        if sem is None:
            return

        wgroup, wcreat = Group.objects.get_or_create(name=settings.WORKER_GROUP)
        bgroup, bcreat = Group.objects.get_or_create(name=settings.BOARD_GROUP)

        workers = User.objects.filter(shiftsignup__shift__semester=sem).distinct()
        for worker in workers:
            if not wgroup in worker.groups.all():
                worker.groups.add(wgroup)

        board_members = User.objects.filter(oncallduty__shift__semester=sem).distinct()
        for board_member in board_members:
            board_member.is_staff = True
            if not bgroup in board_member.groups.all():
                board_member.groups.add(bgroup)
            board_member.save()

        log.info('found %d/%d board/worker member(s)' % (
            len(board_members), len(workers)))

    def _get_styrelse_persids(self):
        c = self._cursor()
        c.execute('''SELECT DISTINCT persid FROM styrelse''')
        fetched = c.fetchall()
        persids = [p['persid'] for p in fetched]
        return persids

    def _norm_sem_day(self, day):
        if self._is_spring(day):
            return date(day.year, 2, 1)
        return date(day.year, 9, 1)

    def _sems_between(self, start, end):
        start_norm = self._norm_sem_day(start)
        end_norm = self._norm_sem_day(end)
        start_sem = self._sem_for_day(start_norm)
        end_sem = self._sem_for_day(end_norm)

        current = start_norm
        added_sem = start_sem
        sems = [added_sem]
        while added_sem != end_sem:
            if self._is_spring(current):
                current = date(current.year, 9, 1)
            else:
                current = date(current.year+1, 2, 1)
            added_sem = self._sem_for_day(current)
            if not added_sem in sems:
                sems.append(added_sem)
        return sems

    def _add_to_board_groups(self, persid):
        decode = self._decode
        c = self._cursor()
        c.execute('''
SELECT * FROM styrelse WHERE persid=%d ORDER BY ts
        ''' % persid)
        fetched = c.fetchall()
        ts_med_post = []
        for row in fetched:
            p = decode(row['post']) if row['post'] else None
            ts_med_post.append(
                [row['ts'], row['med'], p]
            )

        ts_med_post.append([date.today(), 0, None]) # needed for current members

        try:
            ud = self.get_user_dicts(user_id=persid)
            user = User.objects.get(username__exact=decode(ud['login']))
        except:
            log.warning('skipped user with persid=%s' % persid)
            return

        def valid_post(post):
            return post and not post in ('null', '0')

        in_board = False
        last_post = None
        last_became_member = None
        _medsum = 0
        still_board = False
        current_sem = Semester.objects.for_date(date.today())

        bgroup = Group.objects.get(name__exact=settings.BOARD_GROUP)
        for ts, med, post in ts_med_post:
            _medsum += med
            if _medsum == 1:
                if valid_post(post) or last_post:
                    in_board = True
                    still_board = True
                    if last_became_member:
                        log.debug('%r in board' % user)
                    else:
                        last_became_member = ts
                        log.debug('%r in board since %s' % (user, last_became_member))
            elif _medsum == 0:
                still_board = False
            else:
                assert False

            # Hurry board removal if date is too close.
            if med == -1 and ts.month in  (8, 9):
                log.debug("hurried board removal of %r" % user)
                still_board = False
                in_board = False

            if in_board and valid_post(post):
                last_post = post

            if in_board:
                sems = self._sems_between(last_became_member, ts)
                for sem in sems:
                    g = pseudogroups.manual_group_from_semester(bgroup, sem)
                    if not g in user.groups.all():
                        user.groups.add(g)
                        log.info('added %s to %s' % (user, g))

                    if sem == current_sem:
                        if BoardPost.objects.filter(
                                user=user,
                                semester=sem).count():
                            pass
                        else:
                            bpost, created = BoardPost.objects.get_or_create(
                                user=user,
                                semester=sem,
                                post=last_post,
                            )
                            if created:
                                log.info('created %r' % bpost)

            if not still_board:
                in_board = False
                last_became_member = None
                log.debug('%r not in board' % user)

        return fetched


    def setup_board_groups(self):
        c = self._cursor()
        persids = self._get_styrelse_persids()
        decode = self._decode
        for persid in persids:
            self._add_to_board_groups(persid)


    def manual_board(self):
        bgroup, bcreat = Group.objects.get_or_create(name=settings.BOARD_GROUP)
        for uname in manual_board:
            user = User.objects.get(username=uname)
            user.is_staff = True
            if not bgroup in user.groups.all():
                user.groups.add(bgroup)
            user.save()


    def _get_logkort(self):
        c = self._cursor()
        c.execute('''SELECT * FROM logkort''')
        return c.fetchall()


    def _user(self, ud):
        if ud is None:
            return None
        if isinstance(ud, tuple):
            return None
        decode = self._decode
        uname = decode(ud['login']).lower()
        if self._users.has_key(uname):
            user = self._users[uname]
        else:
            try:
                user = User.objects.get(username__exact=uname)
                self._users[uname] = user
            except:
                log.error('user unfound: %s' % uname)
                return None
        return user


    def setup_orders(self):
        logkort = self._get_logkort()
        created_count, skipped = 0, []
        decode = self._decode
        clerk = orders.Clerk()

        # Only import recent orders. Start at the back.
        logkort = list(logkort)
        logkort.sort(key=lambda x: x['ts'], reverse=True)

        users = {}
        goods = orders.default_goods()

        for lk in logkort:
            daytime = lk['ts'].strftime('%Y-%m-%d %H:%M')
            print daytime

            if not lk['persid']:
                skipped.append(lk)
                log.warning('no persid')
                continue

            ud = self.get_user_dicts(user_id=lk['persid'])
            if ud is None:
                log.warning('bad user %d' % lk['persid'])
                skipped.append(lk)
                continue

            if lk['felid'] != 0:
                log.warning('error %d' % lk['felid'])
                skipped.append(lk)
                continue
            
            user = self._user(ud)
            if user is None:
                skipped.append(lk)
                continue

            if Order.objects.filter(user=user, put_at=lk['ts'])[:1].count():
                skipped.append(lk)
                log.warning('already imported (%s), stop now' % daytime)
                break

            preorder = orders.FreePreOrder(user, goods, lk['ts'])
            processed = clerk.process(preorder)
            if processed.accepted():
                log.debug('accepted order for %r (%s)' % (user, daytime))
            else:
                log.debug('denied order for %r (%s)' % (user, daytime))
            created_count += 1

        log.info('%d/%d order(s) created/skipped' % (
            created_count, len(skipped)))

        # This can get very long.
        #if len(skipped):
        #    log.warning('skipped: %s' % ", ".join([str(s) for s in skipped]))


    def _get_sets(self):
        c = self._cursor()
        c.execute('''SELECT * FROM kortset''')
        return c.fetchall()


    def _get_cards(self):
        c = self._cursor()
        c.execute('''SELECT * FROM kaffekort''')
        return c.fetchall()


    def setup_cards_and_sets(self):
        sets = self._get_sets()

        created_count, existing_count, skipped = 0, 0, []
        for s in sets:
            ud = self.get_user_dicts(user_id=s['persid'])
            user = self._user(ud)
            if user is None:
                skipped.append(s)
                continue
            
            try:
                obj, created = OldCoffeeCardSet.objects.get_or_create(
                    set_id=s['id'],
                    made_by=user,
                    file=s['filnamn'],
                    created=s['skapad'],
                )
            except:
                print "skipped %s" % s
                skipped.append(s)
            else:
                obj.time_stamp = s['ts']
                obj.save()
                if created:
                    created_count += 1
                else:
                    existing_count += 1

        log.info('%d/%d/%d old set(s) created/existing/skipped' % (
            created_count, existing_count, len(skipped)))
        if len(skipped):
            log.warning('skipped: %s' % ", ".join([str(s) for s in skipped]))

        created_count, existing_count, skipped = 0, 0, []
        cards = self._get_cards()
        for c in cards:
            ud = self.get_user_dicts(user_id=c['persid'])
            user = self._user(ud)

            set = OldCoffeeCardSet.objects.get(set_id=c['setid'])

            try:
                obj, created = OldCoffeeCard.objects.get_or_create(
                    set=set,
                    user=user,
                    card_id=c['id'],
                    created=c['skapad'],
                    code=c['kod'],
                )
            except:
                print "skipped %s" % c
                skipped.append(c)
            else:
                obj.time_stamp = c['ts']
                obj.count = c['klipp']
                obj.left = c['kvar']
                obj.expires = c['exp']
                obj.save()

                if created:
                    created_count += 1
                else:
                    existing_count += 1

        log.info('%d/%d/%d old card(s) created/existing/skipped' % (
            created_count, existing_count, len(skipped)))
        if len(skipped):
            log.warning('skipped: %s' % ", ".join([str(s) for s in skipped]))

class Command(BaseCommand):
    args = ''
    help = """Import data from the old version of the system. There must be a running MySQL 
server. See OLD_SYSTEM_* settings.
"""

    def handle(self, *args, **options):
        imp = Import()
        imp.setup_users()
        #imp.setup_shifts()
        #imp.setup_oncallduties()
        #imp.setup_current_workers_and_board()
        #imp.manual_board()
        #imp.setup_board_groups()
        imp.setup_orders()
        imp.setup_cards_and_sets()
