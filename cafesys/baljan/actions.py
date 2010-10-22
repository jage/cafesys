# -*- coding: utf-8 -*-

from django.utils.translation import ugettext as _ 
from django.core.urlresolvers import reverse
from django.conf import settings

class Action(object):
    def __init__(self, link_text, path, args=None, kwargs=None, resolve_func=reverse):
        self.text = link_text
        self.active = False
        if resolve_func is None:
            self.link = path
        else:
            self.link = resolve_func(path, args=args, kwargs=kwargs)


def categories_and_actions(request):
    user = request.user
    if user.is_authenticated():
        student = user.get_profile()
    else:
        student = None

    levels = (
        (settings.BOARD_GROUP, _('the board'), (
            Action(_('semesters'), 'baljan.views.current_semester'),
            Action(_('work applications'), '#', resolve_func=None),
            )),
        ('sysadmins', _('sysadmins'), (
            Action(_('django admin site'), 'admin:index'),
            Action(_('munin'), '#', resolve_func=None),
            Action(_('github'), 'http://github.com/pilt/cafesys', resolve_func=None),
            )),
        (settings.WORKER_GROUP, _('workers'), (
            #Action(_('schedule'), 'cal.views.worker_calendar'),
            #Action(_('swaps'), 'cal.views.swappable'),
            )),
        ('regulars', _('students'), (
            #Action(_('recharge card'), 'accounting.views.index'),
            #Action(_('card order history'), 'accounting.views.order_history'),
            Action(_('work for Baljan'), 'become_worker'),
            )),
        ('anyone', _('everyone'), (
            Action(_('work planning'), 'baljan.views.current_semester'),
            Action(_('people and groups'), 'baljan.views.search_person'),
            Action(_('admin site'), 'admin:index'),
            #Action(_('price list'), 'accounting.views.price_list'),
            #Action(_('top lists and order stats'), 'stats.views.index'),
            Action(_('login'), 'acct_login') if student is None else Action(_('logout'), 'acct_logout'),
            )),
        )
    
    if user.is_authenticated():
        for real_group in (settings.BOARD_GROUP, settings.WORKER_GROUP):
            if len(user.groups.filter(name__exact=real_group)):
                group = real_group
                break
        else:
            group = 'regulars'
    else:
        group = 'anyone'

     
    avail_levels = [] 
    for i, action_category in enumerate(levels):
        if group == action_category[0]:
            avail_levels = [list(ita) for ita in levels[i:]]
            break
    
    # Try to find the active section in the accordion. If an exact match is 
    # unfound, a reserve might be. If a reserve is unfound, the last section
    # will be unfolded.
    got_link = False
    active_cls = ' active'
    reserve = None
    for i, action_category in enumerate(avail_levels):
        id, title, acts = action_category
        for act in acts:
            if request.path.startswith(act.link):
                reserve = i
            if request.path == act.link:
                action_category[0] += active_cls
                act.active = True
                got_link = True
                break
        if got_link:
            break
    
    if not got_link:
        if reserve is None:
            avail_levels[-1][0] += active_cls
        else:
            avail_levels[reserve][0] += active_cls

    return avail_levels

