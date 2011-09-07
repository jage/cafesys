
$(document).ready ->
    $('body').click (e) ->
        $('a.menu').parent('li').removeClass 'open'

    $('a.menu').click (e) ->
        $li = $(@).parent 'li'
        $li.siblings().removeClass 'open'
        $li.toggleClass 'open'
        return false
