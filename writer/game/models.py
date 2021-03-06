# -*- coding: utf-8 -*-

from django.db import models
from django.db.models import Q
from django.template import Context
from django.template import Template
import random
from django.template.base import add_to_builtins
import ast
import collections
import re
from slugify import slugify
from django.core.urlresolvers import reverse
import HTMLParser
import writer.collect
import datetime
from django.template.loader import get_template
from writer.promo import get_api
from django.contrib.sitemaps import ping_google
import operator

# Create your models here.

default_used_frases = '{"title": None, "begin": None, "first": None, "group": [], "regular": [], "last": None, "conclusion": None}'


def select_slug(klass, title):
    """
    Select a non-repetitive slug

    :param klass: a class for witch we select the slug
    :type klass: a python class
    :param title: a title from we generate the slug
    :type title: str
    :returns: a non-repetitive slug
    :rtype: str
    """
    slug = slugify(title)
    initial_slug = slugify(title)
    count = 0
    while klass.objects.filter(slug=slug).count():
        count += 1
        slug = '%s-%d' % (initial_slug, count)
    return slug


def mk_sent(what, verb, when, who, how):
    return "%s %s %s %s %s" % (what, verb, when, who, how)


def ch(value):
    words_list = value.split(';')
    return random.sample(words_list, 1)[0]


def list_authors(authors):
    ret = ''
    for i, author in enumerate(authors):
        goals = 'min. '
        goals += ', '.join(authors[author])
        if (i != 0) and (i != len(authors) - 1):
            ret += ', '
        if (i != len(authors) - 1) or (len(authors) == 1):
            ret += '%s (%s)' % (author, goals)
        else:
            ret += u' şi %s (%s) ' % (author, goals)
    return ret


def typo(value):
    value = re.sub(r' ([,\.!\?])', r'\1 ', value)
    value = re.sub(r'([,\.!\?])', r'\1 ', value)
    value = re.sub(' +', ' ', value)
    return value


def get_season():
    """
    It's a helper function for getting the current season. Is used, for example, in creation of game item.

    :returns: the id of current season
    :rtype: int
    """
    return Season.objects.last().id


def sitemap():
    team_list = Team.objects.only('slug', 'campionat').all()
    campionat_list = Campionat.objects.only('slug').all()
    news_list = News.objects.only('slug', 'game').order_by('-pub_date')
    pub_date = news_list.first().pub_date

    template = get_template('sitemap.xml')
    f = open('/var/www/sport-news-writer/sitemap.xml', 'w')
    cont = template.render(Context(locals()))
    f.write(cont)
    f.close()
    ping_google('/sitemap.xml')
    return


class Photo(models.Model):
    title = models.CharField(max_length=1024)
    image = models.ImageField(upload_to='images')

    def __unicode__(self):
        return self.title


class Season(models.Model):
    """
    The model for season. For calculating corrent the current points and the top of teams, we need to work only with the games in current season.
    """
    #: The title of season
    title = models.CharField(max_length=64)

    def __unicode__(self):
        return self.title


class Campionat(models.Model):
    """
    It's a model for league. Used for calculating top, points and so on.
    """
    #: the name of league
    title = models.CharField(max_length=128)
    #: slug pentru human readable urls
    slug = models.CharField(max_length=160, db_index=True)
    #: the url on livescore for collecting games
    url = models.CharField(max_length=1024)
    #: the name of country where the championship is played
    country = models.CharField(max_length=128, blank=True, null=True)

    def __unicode__(self):
        return self.country

    def clasament(self):
        return self.game_set.filter(ft=True).first().render_clasament()


class Player(models.Model):
    """
    The model for player.
    """
    #: The name of player
    name = models.CharField(max_length=128)
    #: The number of goals, marked in this season
    goals_in_season = models.IntegerField(default=0)
    #: The total number of goals marked
    goals_total = models.IntegerField(default=0)
    #: The nationality of player (will be used in making sinonims of his name)
    nationality = models.CharField(max_length=128, blank=True, null=True)
    #: The position of player (like keeper)
    position = models.CharField(max_length=128, blank=True, null=True)
    #: The number of player (for example Alessandro Del Pierro is 7)
    number = models.IntegerField(blank=True, null=True)
    #: A list of fotos of player
    photos = models.ManyToManyField(Photo, blank=True, null=True)

    def __unicode__(self):
        return self.name

    def random_image(self):
        if self.photos.all():
            return random.sample(self.photos.all(), 1)[0]
        return None


class Couch(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ManyToManyField(Photo, blank=True)

    def __unicode__(self):
        return self.name


class Team(models.Model):
    """
    The model for team
    """
    #: The name of team, as it's appear in livescore
    title = models.CharField(max_length=128)
    #: Slug is used for forming human-readable urls
    slug = models.CharField(max_length=160, default='1', db_index=True)
    #: The home city of team (is used in sinonim name forming)
    city = models.CharField(max_length=128, blank=True, null=True)
    #: The name of couch (used in sinonim name forming)
    couch_human = models.ForeignKey(Couch, blank=True, null=True)
    #: The temporary value. If true - the team is host of given game. Is nulled after finish writing news.
    host = models.NullBooleanField(blank=True, null=True)
    #: Temporary value. If true - the team is on first place in league. Is nulled after finish writing news.
    lider = models.NullBooleanField(blank=True, null=True)
    #: Temporary value. If true - the team is on last place in league. Nulled after writing news.
    loser = models.NullBooleanField(blank=True, null=True)
    action = models.CharField(max_length=128, blank=True, null=True)
    #: The league where the team play
    campionat = models.ForeignKey(Campionat)
    #: The seasons when this team play in the campionat
    seasons = models.ManyToManyField(Season)
    #: A list of fotos of team
    photo = models.ManyToManyField(Photo)
    #: Some teams can receive penalities
    penalities = models.IntegerField(default=0)

    def __unicode__(self):
        return self.title

    def etape(self, last_id):
        """How many games was this team played until game with the last_id id in season"""
        season = Game.objects.get(id=last_id).season
        count = Game.objects.filter(season=season).filter(
            (Q(team1=self) | Q(team2=self)) & Q(id__lte=last_id)).count()
        return count

    def act(self, last_id):
        """
        This method return a qualificative of what happend with team in this game.
        It set the proprety self.action to one of the given expressions.

        :param last_id: the id of game
        :type last_id: int
        """
        game = Game.objects.get(id=last_id)
        if game.winer() == self:
            self.action = ch('a cistigat; a invins; a obtinut o victorie')
        elif game.loser() == self:
            self.action = ch('a fost invinsa; a pierdut; a fost infrinta')
        else:
            self.action = ch('a remizat; a obtinut un egal')
        return 'ok'

    def gramar(self, case, plural=None):
        """
        This method give a sinonimical expression to the name of the team.

        :param case: the gramatical case (like nominative, genitive, etc.)
        :type case: char, n|g|a
        """
        variants_s = []
        variants_p = []
        variants = []
        if case == 'n':
            cei = 'cei de la'
            echipa = 'echipa'
            gruparea = 'gruparea'
            gazde = 'gazdele'
            oaspeti = u'oaspeţii'
            elevii = 'elevii'
            lider = 'liderul'
            loser = u'lanterna roşie'
            jucatorii = u'jucătorii'
            fotbalistii = u'fotbaliştii'
            variants_s.append(self.title)
        elif case == 'g':
            cei = 'celor de la'
            gruparea = u'grupării'
            echipa = 'echipei'
            gazde = 'gazdelor'
            oaspeti = u'oaspeţilor'
            elevii = 'elevilor'
            lider = 'liderului'
            loser = u'lanternei roşii a'
            jucatorii = u'jucătorilor'
            fotbalistii = u'fotbaliştilor'
        elif case == 'a':
            cei = 'pe cei de la'
            echipa = 'echipei'
            gruparea = 'gruparea'
            gazde = 'gazdelor'
            oaspeti = u'oaspeţilor'
            elevii = 'elevilor'
            lider = 'liderului'
            loser = u'lanternei roşii a'
            jucatorii = u'jucătorii'
            fotbalistii = u'fotbaliştii'
        if self.city:
            variants_s +=[
                echipa + ' din ' + self.city,
                gruparea + ' din ' + self.city
            ]
        if self.couch_human:
            variants_s += [
                echipa + ' lui ' + self.couch_human.name,
                gruparea + ' lui ' + self.couch_human.name,
            ]
            variants_p += [
                elevii + ' lui ' + self.couch_human.name,
                jucatorii + ' lui ' + self.couch_human.name,
                fotbalistii + ' lui ' + self.couch_human.name
            ]
        variants_p += [
            cei + ' ' + self.title,
        ]
        if self.host:
            variants_s.append(echipa + ' gazda')
            variants_p.append(gazde)
        else:
            variants_s.append(echipa + ' oaspete')
            variants_p.append(oaspeti)
        if self.lider:
            variants_s.append(lider + ' clasamanetului')
            variants_s.append(lider + ' campionatului')
        elif self.loser:
            variants_s.append(loser + ' clasamentului')
            variants_s.append(loser + ' campionatului')
        if plural is None:
            variants = variants_s + variants_p
        elif not plural:
            variants = variants_s
        else:
            variants = variants_p
        return '<strong><a href="%s" title="%s">%s</a></strong>' % (reverse('team', kwargs={'campionat': self.campionat.slug, 'team': self.slug}), self.title, random.sample(variants, 1)[0])

    def n(self):
        """
        The shortcut for self.gramar('n')
        """
        return self.gramar('n')

    def g(self):
        return self.gramar('g')

    def a(self):
        return self.gramar('a')

    def ns(self):
        return self.gramar('n', False)

    def np(self):
        return self.gramar('n', True)

    def gs(self):
        return self.gramar('g', False)

    def gp(self):
        return self.gramar('g', True)

    def wining_trend(self, last_id=None):
        """
        Identify the wining trend. If the team win a several games consecutivly, it returns a number of wins.

        :param last_id: the id of game
        :type last_id: int
        :returns: the number of wins
        :rtype: int
        """
        args = Q(team1=self)
        args |= Q(team2=self)
        if not last_id:
            last_id = Game.objects.first().id
        args &= Q(id__lte=last_id)
        wins = 0
        for game in Game.objects.filter(args).order_by('-id'):
            if game.winer() == self:
                wins += 1
            else:
                break
        return wins

    def non_lose_trend(self, last_id=None):
        args = Q(team1=self)
        args |= Q(team2=self)
        if not last_id:
            last_id = Game.objects.first().id
        args &= Q(id__lte=last_id)
        wins = 0
        for game in Game.objects.filter(args).order_by('-id'):
            if game.loser() != self:
                wins += 1
            else:
                break
        return wins

    def partide(self, last_id=None):
        return self.etape(last_id)

    def lose_trend(self, last_id=None):
        args = Q(team1=self)
        args |= Q(team2=self)
        if not last_id:
            last_id = Game.objects.first().id
        args &= Q(id__lte=last_id)
        lose = 0
        for game in Game.objects.filter(args).order_by('-id'):
            if game.loser() == self:
                lose += 1
            else:
                break
        return lose

    def goals_diff(self, last_id=None):
        args = Q(team1=self)
        args |= Q(team2=self)
        if not last_id:
            last_id = Game.objects.first().id
        ref_game = Game.objects.get(id=last_id)
        season = ref_game.season
        args &= Q(season=season)
        args &= Q(id__lte=last_id)
        (goals_in, goals_out) = (0, 0)
        for game in Game.objects.filter(args).order_by('id'):
            if game.team1 == self:
                goals_out += game.goal_team1
                goals_in += game.goal_team2
            else:
                goals_in += game.goal_team1
                goals_out += game.goal_team2
        return goals_out - goals_in

    def points(self, last_id=None):
        args = Q(team1=self)
        args |= Q(team2=self)
        if not last_id:
            last_id = Game.objects.first().id
        ref_game = Game.objects.get(id=last_id)
        season = ref_game.season
        args &= Q(season=season)
        args &= Q(id__lte=last_id)
        points = 0
        for game in Game.objects.filter(args).order_by('id'):
            if game.winer() == self:
                points += 3
            elif game.loser() == self:
                pass
            else:
                points += 1
        return points - self.penalities

    def loc(self, last_id=None):
        loc = -1
        if not last_id:
            last_id = Game.objects.first().id
        args = Q(id__lte=last_id) & Q(campionat=self.campionat)
        game = Game.objects.filter(args).first()
        clasament = game.clasament()
        for i, element in enumerate(clasament):
            if element[1] == self.id:
                loc = i
        return loc + 1

    def loc_prev(self, last_id=None):
        if not last_id:
            last_id = Game.objects.first().id
        if last_id:
            return self.loc(last_id - 1)
        return None

    def vecini(self, last_id=None):
        """
        Returns the team upper and the team lower in the top.

        :param last_id: the id of current game
        :type last_id: int
        :returns: a tuple with the team upper and lower then current team
        :rtype: tuple
        """
        if not last_id:
            last_id = Game.objects.first().id
        game = Game.objects.get(id=last_id)
        clasament = game.clasament()
        loc = self.loc()
        if loc > 1:
            upper = clasament[loc - 2]
            upper = Team.objects.get(id=upper)
        else:
            upper = None
        if loc != len(clasament):
            lower = clasament[loc + 1]
            lower = Team.objects.get(id=lower)
        else:
            lower = None
        return upper, lower


class Goal(models.Model):
    author = models.ForeignKey(Player, blank=True, null=True)
    assist = models.ForeignKey(Player, blank=True, null=True, related_name='assist_goal')
    minute = models.IntegerField()
    team = models.ForeignKey(Team)
    penalty = models.BooleanField(default=False)
    auto = models.BooleanField(default=False)
    recipient = models.ForeignKey(Team, related_name='recipient_team', blank=True, null=True)

    def __unicode__(self):
        return self.author.name

    def what(self):
        v = []
        if self.equal():
            v += [
                '%s care a readus balanta pe tabloul de marcaj' % ch('golul; balonul; reusita; sutul precis'),
                '%s care a readus scorul la egal' % ch('golul; balonul; reusita; sutul precis'),
            ]
        elif self.reverse():
            v += [
                'golul care a intors situatia' % ch('golul; balonul; reusita; sutul precis'),
                'golul care a schimbat balanta de forte pe tabloul de marcaj' % ch('golul; balonul; reusita; sutul precis'),
                'intoarcerea de scor',
                'golul care a rasturnat situatia' % ch('golul; balonul; reusita; sutul precis'),
            ]
        elif self.victory():
            v += [
                'golul victoriei',
                'golul decisiv',
                'golul care a decis rezultatul partidei' % ch('golul; balonul; reusita; sutul precis'),
                'golul care a salvat situatia' % ch('golul; balonul; reusita; sutul precis'),
                'golul care a adus victoria' % ch('golul; balonul; reusita; sutul precis')
            ]
        elif self.auto:
            v += [
                'autogolul',
            ]
        elif self.penalty:
            v += [
                'lovitura de pedeapsa',
                'penalty-ul',
            ]
        else:
            v += [
                'golul',
            ]
        return random.sample(v, 1)[0]

    def how(self):
        v = []
        if self.penalty:
            v += [
                'din penalty',
                'dintr-o lovitura de pedeapsa',
                'dupa executia unei lovituri de pedeapsa'
            ]
        elif self.assist:
            v += [
                'cu concursul lui %s' % self.assist.name,
                'din pasa lui %s' % self.assist.name,
                'fiind asistat de %s' % self.assist.name,
                'ajutat de %s' % self.assist.name,
            ]
        else:
            v += [
                '',
            ]
        return random.sample(v, 1)[0]

    def score(self):
        game = self.game_set.first()
        goal_list = list(game.goals.order_by('minute'))
        index = goal_list.index(self)
        score = game.scor_list()[index]
        return '%d:%d' % (score[0], score[1])

    def only(self):
        only = True
        for goal in self.game_set.first().goals.all():
            if (goal.team == self.team) and (goal != self):
                only = False
        return only

    def reverse(self):
        scor_list = self.game_set.first().scor_list()
        order = list(self.game_set.first().goals.all()).index(self)
        if (order > 1) and (((scor_list[order][0] - scor_list[order][1]) * (scor_list[order-2][0] - scor_list[order-2][1])) < 0):
            return True
        return False

    def equal(self):
        scor_list = self.game_set.first().scor_list()
        order = list(self.game_set.first().goals.all()).index(self)
        if scor_list[order][0] == scor_list[order][1]:
            return True
        return False

    def victory(self):
        prev_equal = False
        try:
            prev_last = self.game_set.first().scor_list()[-2]
            if prev_last[0] == prev_last[1]:
                prev_equal = True
        except:
            prev_equal = True

        if (self == self.game_set.first().goals.last()) and prev_equal:
            return True
        return False

    def egalizator(self):
        if (self == self.game_set.first().goals.last()) and self.equal():
            return True
        return False

    def m(self):
        m = self.minute
        order = list(self.game_set.first().goals.all()).index(self)
        v = []
        if (m < 44) and (m > 30):
            diff = 45 - m
            b_s = u'cu %d minute înainte de' % diff
            if diff == 15:
                b_s = u'cu un sfert de oră înainte de'
            elif diff == 30:
                b_s = u'cu o jumatate de oră înainte de'
            v += [
            '%s finalul primei reprize' % b_s,
            '%s a pleca la vestiare' % b_s,
            u'cu %d minute până la pauză' % diff,
            '%s finalul primului mitan' % b_s,
            ]
        elif (m < 88) and (m > 75):
            diff = 90 - m
            b_s = u'cu %d minute înainte de' % diff
            if diff == 15:
                b_s = u'cu un sfert de oră înainte de'
            elif diff == 30:
                b_s = u'cu o jumătate de oră înainte de'
            v += [
            '%s finalul reprizei secunde' % b_s,
            '%s a fluierul final' % b_s,
            '%s finalul meciului' % b_s,
            '%s terminarea timpului regulamentar' % b_s,
            ]
        prev_goal_diff = False
        if order > 0:
            prev_goal_diff = m - self.game_set.first().goals.all()[order - 1].minute
        if (order > 0) and (prev_goal_diff < 15) and (prev_goal_diff > 1):
            v += [
                u'%d minute mai târziu' % (m - self.game_set.first().goals.all()[order - 1].minute),
                u'după încă %d minute' % (m - self.game_set.first().goals.all()[order - 1].minute),
            ]
        elif prev_goal_diff and (prev_goal_diff < 2):
            v += [
                u'câteva clipe mai târziu',
                u'câteva secunde mai târziu',
                u'după câteva clipe',
                u'după câteva secunde',
            ]
        v += [
            u'în minutul %d' % m,
        ]
        return random.sample(v, 1)[0]


class Carton(models.Model):
    player = models.ForeignKey(Player)
    minute = models.IntegerField()
    red = models.BooleanField(default=False)
    cumul = models.BooleanField(default=False)
    team = models.ForeignKey(Team)

    def __unicode__(self):
        return self.player.name


class Game(models.Model):
    campionat = models.ForeignKey(Campionat, blank=True, null=True)
    team1 = models.ForeignKey(Team, related_name='game_team1')
    team2 = models.ForeignKey(Team, related_name='game_team2')
    goal_team1 = models.IntegerField(default=0)
    goal_team2 = models.IntegerField(default=0)
    pub_date = models.DateField(blank=True, null=True, db_index=True)
    game_time = models.TimeField(blank=True, null=True)
    goals = models.ManyToManyField(Goal, blank=True, null=True)
    cartons = models.ManyToManyField(Carton, blank=True, null=True)
    url = models.CharField(max_length=512, blank=True, null=True)
    classament = models.TextField(blank=True, null=True)
    classament_rendered = models.TextField(blank=True, null=True)
    season = models.ForeignKey(Season, default=get_season)
    images = models.ManyToManyField(Photo, blank=True)
    video = models.TextField(blank=True, null=True)
    live = models.TextField(blank=True, null=True)
    used_frases = models.TextField(default=default_used_frases)
    ft = models.BooleanField(default=True)

    class Meta:
        index_together = [
            ['pub_date', 'campionat'],
            ['pub_date', 'campionat', 'season'],
        ]
        ordering = ['-pub_date', '-id']

    def __unicode__(self):
        return self.team1.title + ' ' + str(self.goal_team1) + ':' + str(self.goal_team2) + ' ' + self.team2.title

    ###########
    # Methods #
    ###########
    def score(self):
        return str(self.goal_team1) + ':' + str(self.goal_team2)

    def hero(self):
        if self.goals.count():
            dummy = {'goals': 0, 'assist': 0, 'victory': 0, 'equal': 0, 'auto': 0,
                    'assist_victory': 0}
            points = {}
            players = {}
            for goal in self.goals.all():
                player = players.get(goal.author, None)
                assist = players.get(goal.assist, None)
                if not player:
                    players[goal.author] = dummy.copy()
                if (not assist) and goal.assist:
                    players[goal.assist] = dummy.copy()
                if not goal.auto:
                    players[goal.author]['goals'] += 1
                    if goal.assist:
                        players[goal.assist]['assist'] += 1
                else:
                    players[goal.author]['auto'] += 1
                if goal.victory() and not goal.auto:
                    players[goal.author]['victory'] += 1
                    if goal.assist:
                        players[goal.assist]['assist_victory'] += 1
                if goal.egalizator() and not goal.auto:
                    players[goal.author]['equal'] += 1
                    if goal.assist:
                        players[goal.assist]['assist_victory'] += 1
            for author in players:
                points[author] = (players[author]['goals'] * 2) + players[author]['assist'] + (players[author]['victory'] * 4) + (players[author]['assist_victory'] * 2) + (players[author]['equal'] * 3) - (players[author]['auto'] * 3)
            hero = sorted(points, key=points.get, reverse=True)[0]
            return {'player': hero, 'points': points[hero], 'data': players[hero], 'game': self}
        return None

    def class_difference(self):
        return abs(self.team1.points(self.id) - self.team2.points(self.id))

    def lideri(self):
        if (self.team1.loc(self.id) in [1, 2, 3]) and (self.team2.loc(self.id) in [1, 2, 3]):
            return True
        return False

    def surprise(self):
        if self.class_difference() > 10:
            if not self.winer():
                return True
            if self.winer().points() < self.loser().points():
                return True
        return False

    def render_clasament(self):
        """
        This method will render the clasament.
        """
        if self.classament_rendered:
            return ast.literal_eval(self.classament_rendered)
        clasament = self.clasament()
        res = []
        for row in clasament:
            (points, team_id, goals_diff) = row
            team = Team.objects.get(id=team_id)
            (count, wins, loses, equals, goals_in, goals_out) = [0]*6
            for game in Game.objects.filter(
                Q(season=self.season) &
                Q(pub_date__lte=self.pub_date) & Q(id__lte=self.id) &
                (Q(team1=team) | Q(team2=team))
            ).all():
                count += 1
                if game.winer() == team:
                    wins += 1
                elif game.loser() == team:
                    loses += 1
                else:
                    equals += 1
                if game.team1 == team:
                    goals_out += game.goal_team1
                    goals_in += game.goal_team2
                else:
                    goals_in += game.goal_team1
                    goals_out += game.goal_team2
            res.append({
                'campionat': self.campionat.title,
                'pub_date': self.pub_date.strftime('%d.%m.%Y'),
                'team': team.title,
                'points': points,
                'goals_in': goals_in,
                'goals_out': goals_out,
                'wins': wins,
                'loses': loses,
                'equals': equals
            })
        self.classament_rendered = str(res)
        self.save()
        return res

    def clasament(self, regenerate=False):
        if not self.classament or (len(self.classament) < 10) or regenerate:
            clasament = []
            for team in self.campionat.team_set.filter(seasons=self.season).all():
                points = team.points(self.id)
                diff = team.goals_diff(self.id)
                clasament.append([points, team.id, diff])
            clasament.sort(key = operator.itemgetter(0, 2))
            clasament.reverse()
            self.classament = str(clasament)
            self.save()
        return ast.literal_eval(self.classament)

    def urcare(self):
        urcare = []
        if self.team1.etape(self.id) > 7:
            for team in [self.team1, self.team2]:
                if team.loc(self.id) < team.loc_prev(self.id):
                    loc = team.loc(self.id)
                    prev_game = Game.objects.filter(Q(campionat=self.campionat) & Q(id__lt=self.id)).first()
                    declasat_id = prev_game.clasament()[loc - 1][1]
                    declasat = Team.objects.get(id=declasat_id)
                    urcare.append([team, loc, team.points(self.id), declasat, declasat.points(self.id), declasat.loc(self.id)])
            if len(urcare) > 0:
                return urcare
        return False

    def coborire(self):
        coborire = []
        if self.team1.etape(self.id) > 7:
            for team in [self.team1, self.team2]:
                if team.loc(self.id) > team.loc_prev(self.id):
                    loc = team.loc(self.id)
                    prev_game = Game.objects.filter(Q(campionat=self.campionat) & Q(id__lt=self.id)).first()
                    supraclasat_id = prev_game.clasament()[loc - 1][1]
                    supraclasat = Team.objects.get(id=supraclasat_id)
                    coborire.append([team, loc, team.points(self.id), supraclasat, supraclasat.points(self.id), supraclasat.loc(self.id)])
            if len(coborire) > 0:
                return coborire
        return False

    def lupta_loc(self):
        if self.team1.etape(self.id) > 7:
            if self.team1.points(self.id - 1) == self.team2.points(self.id - 1):
                return True
        return False

    def scor_list(self):
        scor_list = []
        scor = [0, 0]
        for goal in self.goals.order_by('minute'):
            if goal.team == self.team1:
                scor[0] += 1
            else:
                scor[1] += 1
            scor_list.append([scor[0], scor[1]])
        return scor_list

    def intoarcere(self):
        scor_list = self.scor_list()
        if len(scor_list) > 2:
            for i in range(2, len(scor_list)):
                if ((scor_list[i][0] - scor_list[i][1]) * (scor_list[i-2][0] - scor_list[i-2][1])) < 0:
                    return True
        return False

    def duble(self):
        duble = []
        for goal in self.goals.all():
            if self.goals.filter(author=goal.author).exclude(id=goal.id).count() == 1:
                duble.append(goal.author)
        return list(set(duble))

    def triple(self):
        triple = []
        for goal in self.goals.all():
            if self.goals.filter(author=goal.author).exclude(id=goal.id).count() == 2:
                triple.append(goal.author)
        return list(set(triple))

    def winer(self):
        if self.goal_team1 > self.goal_team2:
            return self.team1
        elif self.goal_team2 > self.goal_team1:
            return self.team2
        else:
            return None

    def loser(self):
        if self.goal_team1 > self.goal_team2:
            return self.team2
        elif self.goal_team2 > self.goal_team1:
            return self.team1
        else:
            return None

    def score_diference(self):
        return abs(int(self.goal_team1) - int(self.goal_team2))

    def total_goals(self):
        return int(self.goal_team1) + int(self.goal_team2)

    def only(self):
        if self.total_goals() == 1:
            return True
        return False

    def last_goal_final(self):
        """This method tell us if the last goal was on final of the game and was decisive for the result"""
        last_goal = self.goals.last()
        if last_goal and (last_goal.minute > 80) and (last_goal.victory() or last_goal.equal()):
            return True
        return False

    def goals_set(self):
        goals = []
        if self.goals.count():
            group = []
            for goal in self.goals.all():
                if not group:
                    team = goal.team
                if team == goal.team:
                    group.append(goal)
                else:
                    goals.append(group)
                    group = [goal]
                    team = goal.team
            goals.append(group)
        return goals

    def precedent_game(self):
        game = Game.objects.filter(
            Q(pub_date__lt=self.pub_date) &
            (
                (Q(team1=self.team1) & Q(team2=self.team2)) |
                (Q(team1=self.team2) & Q(team2=self.team1))
            )
        ).first()
        if game:
            return game, (self.pub_date - game.pub_date).days/30
        return None

    #############
    # Templates #
    #############
    def title_frase(self, debug=False, begin=False):
        exclude = Q()
        if begin:
            exclude = Q(id=self.used['title'])
        not_null = Q(title__isnull=False)
        diff = Q(min_score_diference__lte=self.score_diference()) & Q(max_score_diference__gte=self.score_diference())
        diff_null = Q(min_score_diference__isnull=True) & Q(max_score_diference__isnull=True)
        total = Q(min_total_goals__lte=self.total_goals()) & Q(max_total_goals__gte=self.total_goals())
        total_null = Q(max_total_goals__isnull=True, min_total_goals__isnull=True)
        last_final = Q(last_goal_final=self.last_goal_final())

        diff_set = diff & total_null & last_final
        total_set = total & diff_null
        goal_set = diff & total
        sets = [diff_set, total_set, goal_set]

        wins = False
        loses = False
        if self.winer():
            wins = self.winer().wining_trend(self.id)
            if self.winer().wining_trend(self.id) >= 4:
                win_set = Q(win_ser=True)
                sets = [win_set]
            if self.team1.etape(self.id) > 7:
                if self.winer().loc(self.id) == 1:
                    sets.append(Q(with_champion=True))
        if self.loser():
            loses = self.loser().lose_trend(self.id)
            if self.loser().lose_trend(self.id) >= 3:
                lose_set = Q(lose_ser=True)
                sets = [lose_set]
            if self.team1.etape(self.id) > 7:
                if self.loser().loc_prev(self.id) == 1:
                    sets.append(Q(with_champion=False))

        for i, args in enumerate(sets):
            if i == 0:
                res = TitleFrase.objects.filter(args).filter(not_null).exclude(exclude).all()
            else:
                res |= TitleFrase.objects.filter(args).filter(not_null).exclude(exclude).all()
        frase = random.sample(res, 1)[0]
        tpl_string = frase.title
        tpl = Template(tpl_string)
        ret = ''
        if debug:
            ret += '(%d)' % frase.id
        ret += tpl.render(Context({'game': self, 'wins': wins, 'loses': loses}))
        try:
            if not begin:
                self.used['title'] = frase.id
            else:
                self.used['begin'] = frase.id
        except:
            pass
        return ret

    def previouse_game_frase(self, debug=False):
        args = Q()
        precedent_game_data = self.precedent_game()
        res = ''
        if precedent_game_data:
            (pg, delta) = precedent_game_data
            loser = pg.loser()
            (lose, success, equal) = (False, False, False)
            if loser:
                lose = True
            if self.winer() == loser:
                success = True
            if not self.loser():
                equal = True
            if success and equal:
                success = False
            args &= Q(loser=lose) & Q(succes=success) & Q(equal=equal)
            if debug:
                print 'params', lose, success, equal
            frase = random.sample(PreviouseGameFrase.objects.filter(args).all(), 1)[0]
            tpl_string = frase.title
            tpl = Template(tpl_string)
            if debug:
                res += '(%d)' % frase.id
            res += tpl.render(Context({'game': pg, 'loser': loser, 'delta': delta}))
        return res

    def first_goal_frase(self, debug=False):
        args = Q()
        args &= Q(only=self.only())
        args &= Q(min_minute__lte=self.goals.all()[0].minute)
        args &= Q(max_minute__gte=self.goals.all()[0].minute)
        args &= Q(title__isnull=False)
        frase = random.sample(FirstGoalFrase.objects.filter(args).all(), 1)[0]
        tpl = Template(frase.title)
        ret = ''
        if debug:
            ret += '(%d)' % frase.id
        ret += tpl.render(Context({'game': self,}))
        self.used['first'] = frase.id
        return ret

    def group_goals_frase(self, group, i, total, debug=False):
        reg_goals = ''
        if i == 0:
            group.pop(0)
        if i == total - 1:
            group = group[:-1]
        if len(group) > 1:
            authors = collections.OrderedDict()
            for goal in group:
                cg = authors.get(goal.author.name, [])
                authors[goal.author.name] = cg + [str(goal.minute)]
            goals = list_authors(authors)
            if i == 0:
                first = True
            else:
                first = False
            args = Q(first=first)
            if group[-1].equal():
                args &= Q(equal=True)
            elif group[-1].reverse():
                args &= Q(reverse=True)
            frase = random.sample(GoalGroupFrase.objects.filter(args).exclude(
                id__in=self.used['group']
            ).all(), 1)[0]
            goal_group_frase = Template(frase.title)
            team = group[0].team
            recipient = group[0].recipient
            score = group[-1].score()
            reg_goals += goal_group_frase.render(Context({
                'team': team, 'recipient': recipient, 'score': score, 'authors': goals}))
            self.used['group'].append(frase.id)
        elif len(group) == 1:
            reg_goals += ' %s' % self.regular_goal_frase(group[0], debug)
        return reg_goals

    def regular_goal_frase(self, goal, debug=False):
        exclude = Q()
        exclude = Q(id__in=self.used['regular'])
        args = Q()
        if goal.only() and goal.equal():
            args &= Q(only=goal.only())
        else:
            args &= Q(only=goal.only())
            args &= Q(equal=goal.equal())
        args &= Q(reverse=goal.reverse())
        args &= Q(duble=False)
        args &= Q(triple=False)
        frase = random.sample(RegularGoalFrase.objects.filter(args).exclude(exclude).all(), 1)[0]
        tpl = Template(frase.title)
        ret = ''
        if debug:
            ret += '(%d)' % frase.id
        ret += tpl.render(Context({'goal': goal,}))
        self.used['regular'].append(frase.id)
        return ret

    def last_goal_frase(self, debug=False):
        last_goal = self.goals.last()
        scor_list = self.scor_list()
        pre_last_scor = scor_list[len(scor_list) - 2]
        args = Q()
        only = False
        if ((last_goal.team == self.team1) and (self.goal_team1 == 1)) or ((last_goal.team == self.team2) and (self.goal_team2 == 1)):
            only = True
        equal = (self.goal_team1 == self.goal_team2)
        victory = (pre_last_scor[0] == pre_last_scor[1])
        reverse = False
        if (len(scor_list) > 3) and (((scor_list[-1][0] - scor_list[-1][1]) * (scor_list[-2][0] - scor_list[-2][1])) < 0):
            reverse = True
        args &= Q(reverse=reverse)
        args &= Q(only=only)
        args &= Q(equal=equal)
        args &= Q(victory=victory)
        args &= Q(title__isnull=False)
        frase = random.sample(LastGoalFrase.objects.filter(args).all(), 1)[0]
        tpl = Template(frase.title)
        ret = ''
        if debug:
            ret += '(%d)' % frase.id
        ret += tpl.render(Context({'game': self, 'goal': last_goal}))
        self.used['last'] = frase.id
        return ret

    def conclusion(self, debug=False):
        args = Q()
        args &= Q(urcare=(self.urcare() is not False))
        args &= Q(coborire=(self.coborire() is not False))
        frase = random.sample(Conclusion.objects.filter(args).all(), 1)[0]
        tpl = Template(frase.title)
        var = {
            'game': self,
            'loc1': self.team1.loc(self.id), 'loc2': self.team2.loc(self.id),
            'puncte1': self.team1.points(self.id), 'puncte2': self.team2.points(self.id)
        }
        coborire = self.coborire()
        urcare = self.urcare()
        if urcare:
            var['urc_team'] = urcare[0][0]
            var['urc_loc'] = urcare[0][1]
            var['urc_points'] = urcare[0][2]
            var['declasat'] = urcare[0][3]
            var['declasat_points'] = urcare[0][4]
            var['declasat_loc'] = urcare[0][5]
        if coborire:
            var['cob_team'] = coborire[0][0]
            var['cob_loc'] = coborire[0][1]
            var['cob_points'] = coborire[0][2]
            var['supraclasat'] = coborire[0][3]
            var['supraclasat_points'] = coborire[0][4]
            var['supraclasat_loc'] = coborire[0][5]
        ret = ''
        if debug:
            ret += '(%d)' % frase.id
        ret += tpl.render(Context(var))
        self.used['conclusion'] = frase.id
        return ret

    ###############
    # Making news #
    ###############
    def start(self):
        self.used = ast.literal_eval(self.used_frases)
        self.team1.host = True
        for team in [self.team1, self.team2]:
            if team.etape(self.id) > 7:
                if team.loc(self.id - 1) == 1:
                    team.lider = True
                elif team.loc(self.id - 1) == len(self.clasament()):
                    team.loser = True
            team.act(last_id=self.id)
            team.save()

    def stop(self):
        self.used_frases = str(self.used)
        self.save()
        Synonims.objects.all().update(used=None)
        for team in [self.team1, self.team2]:
            team.host = False
            team.lider = False
            team.loser = False
            team.action = ''
            team.save()

    def select_image(self):
        if self.images.count():
            return random.sample(self.images.all(), 1)[0]
        elif Game.objects.filter((Q(team1=self.team1, team2=self.team2) | Q(team2=self.team1, team1=self.team2)) & Q(images__isnull=False)).count():
            g = Game.objects.filter((Q(team1=self.team1, team2=self.team2) | Q(team2=self.team1, team1=self.team2)) & Q(images__isnull=False)).first()
            return random.sample(g.images.all(), 1)[0]
        elif Photo.objects.filter(player__goal__game=self).count():
            return random.sample(Photo.objects.filter(player__goal__game=self).all(), 1)[0]
        elif self.winer() and self.winer().photo.count():
            return random.sample(self.winer().photo.all(), 1)[0]
        elif not self.winer() and self.team1.photo.count():
            return random.sample(self.team1.photo.all(), 1)[0]
        else:
            try:
                writer.collect.collect_photo(g=self)
            except: pass
            for goal in self.goals.all():
                for player in [goal.author, goal.assist]:
                    if player and not player.photos.count():
                        try: writer.collect.collect_photo(player=player)
                        except: pass
            for team in [self.team1, self.team2]:
                if not team.photo.count():
                    try: writer.collect.collect_photo(team=team)
                    except: pass
            return random.sample(self.images.all(), 1)[0]
        return None

    def news(self, debug=False, regenerate=False):
        self.start()
        news = None
        if regenerate and self.news_set.first():
            news = self.news_set.first()
            self.used_frases = default_used_frases
            self.save()
            self.used = ast.literal_eval(self.used_frases)
        title = self.title_frase(debug)
        begin_frase = self.title_frase(debug, begin=True)
        precedent_frase = self.previouse_game_frase(debug)
        """
        if self.lupta_loc():
            begin_frase += u' În această seară cele două echipe au luptat pentru dreptul de a ocupa locul ' + str(max(self.team1.loc(self.id), self.team2.loc(self.id))) + '. '
        """
        first_goal_frase = ''
        if self.goals.count() > 0:
            first_goal_frase = self.first_goal_frase(debug)
        reg_goals = ''
        if self.goals.count() > 2:
            goals_set = self.goals_set()
            for i, group in enumerate(goals_set):
                reg_goals += self.group_goals_frase(group, i, len(goals_set), debug)
        last_goal_frase = ''
        if self.goals.count() > 1:
            last_goal_frase = self.last_goal_frase(debug)
        conclusion = ''
        if self.team1.etape(self.id) > 7:
            conclusion = self.conclusion(debug)
        html_parser = HTMLParser.HTMLParser()
        news_text = """
                    <p><b>%s</b></p>
                    <p>%s</p>
                    <p>%s</p>
                    <p>%s</p>
                    <p>%s</p>
                    <p><b>%s</b></p>
                    """ % (html_parser.unescape(begin_frase), html_parser.unescape(precedent_frase), html_parser.unescape(first_goal_frase), html_parser.unescape(reg_goals), html_parser.unescape(last_goal_frase), html_parser.unescape(conclusion))
        news_text = typo(news_text)
        if not debug:
            if not news:
                image = self.select_image()
                if image:
                    slug = select_slug(News, title)
                    news = News(title=title, text=news_text, photo=image, pub_date=datetime.datetime.now(), game=self, slug=slug)
                    news.save()
                    sitemap()
            else:
                news.title = title
                news.text = news_text
                news.save()
        else:
            self.used = ast.literal_eval(default_used_frases)
        self.stop()
        return news


class TitleFrase(models.Model):
    title = models.TextField(blank=True, null=True)
    min_score_diference = models.IntegerField(blank=True, null=True)
    max_score_diference = models.IntegerField(blank=True, null=True)
    min_total_goals = models.IntegerField(blank=True, null=True)
    max_total_goals = models.IntegerField(blank=True, null=True)
    last_goal_final = models.BooleanField(default=False)
    triple = models.BooleanField(default=False)
    duble = models.BooleanField(default=False)
    urcare = models.BooleanField(default=False)
    coborire = models.BooleanField(default=False)
    win_ser = models.BooleanField(default=False)
    stop_win_ser = models.BooleanField(default=False)
    lose_ser = models.BooleanField(default=False)
    stop_lose_ser = models.BooleanField(default=False)
    nonlose_ser = models.BooleanField(default=False)
    stop_nonlose_ser = models.BooleanField(default=False)
    with_champion = models.NullBooleanField(default=None)

    def __unicode__(self):
        ret = ''
        if self.title:
            ret += self.title
        ret += '. Score diff: ' + str(self.min_score_diference) + ' - ' + str(self.max_score_diference) + '. Total: ' + str(self.min_total_goals) + ' - ' + str(self.max_total_goals)
        return ret


class FirstGoalFrase(models.Model):
    title = models.TextField(blank=True, null=True)
    min_minute = models.IntegerField(blank=True, null=True)
    max_minute = models.IntegerField(blank=True, null=True)
    only = models.BooleanField(default=False)

    def __unicode__(self):
        ret = ''
        if self.title:
            ret += self.title + '. '
        ret += str(self.min_minute) + ' - ' + str(self.max_minute)
        return ret


class PreviouseGameFrase(models.Model):
    #: the frase itself
    title = models.TextField()
    #: someone have lose in this game?
    loser = models.BooleanField()
    #: the loser wins?
    succes = models.BooleanField()
    #: or it was an equal?
    equal = models.BooleanField()

    def __unicode__(self):
        return self.title


class RegularGoalFrase(models.Model):
    title = models.TextField(blank=True, null=True)
    equal = models.BooleanField(default=False)
    reverse = models.BooleanField(default=False)
    only = models.BooleanField(default=False)
    duble = models.BooleanField(default=False)
    triple = models.BooleanField(default=False)

    def __unicode__(self):
        if self.title:
            return self.title
        else:
            return ''


class GoalGroupFrase(models.Model):
    """
    It's a model for groups of goals (the cases when the same team mark more then 1 goal consecutivly.
    """
    #: the template for frase
    title = models.TextField()
    #: is this group the first group in game?
    first = models.BooleanField(default=False)
    #: have someone from the authors mark 2 goals in this game?
    duble = models.BooleanField(default=False)
    #: have someone from the authors mark 3 goals in this game?
    triple = models.BooleanField(default=False)
    #: have someone from the authors mark more then 3 goals in this game?
    more = models.BooleanField(default=False)
    #: after last goal is equal?
    equal = models.BooleanField(default=False)
    #: after last goal is reverse of score?
    reverse = models.BooleanField(default=False)

    def __unicode__(self):
        return self.title


class LastGoalFrase(models.Model):
    title = models.TextField(blank=True, null=True)
    equal = models.BooleanField(default=False)
    reverse = models.BooleanField(default=False)
    only = models.BooleanField(default=False)
    victory = models.BooleanField(default=False)

    def __unicode__(self):
        ret = ''
        if self.title:
            ret += self.title
        else:
            ret = 'None'
        return ret


class Conclusion(models.Model):
    title = models.TextField(blank=True, null=True)
    urcare = models.BooleanField(default=False)
    coborire = models.BooleanField(default=False)

    def __unicode__(self):
        return self.title


class News(models.Model):
    title = models.CharField(max_length=512)
    slug = models.CharField(max_length=1024, blank=True, null=True, db_index=True)
    text = models.TextField()
    game = models.ForeignKey(Game)
    photo = models.ForeignKey(Photo, blank=True)
    pub_date = models.DateTimeField(db_index=True)

    def __unicode__(self):
        return self.title

    def post_to_facebook(self):
        attachment = {
            'name': self.title.encode('utf-8'),
            'link': 'http://www.fotbal.md%s' % reverse('news', kwargs={'campionat': self.game.campionat.slug, 'title': self.slug}),
            'caption': self.game.title_frase().encode('utf-8'),
            'description': '%s %s' % (self.game.title_frase().encode('utf-8'), self.game.previouse_game_frase().encode('utf-8')),
            'picture': 'http://www.fotbal.md%s' % self.photo.image.url
        }
        graph = get_api()
        graph.put_wall_post(message='', attachment=attachment)


class Synonims(models.Model):
    title = models.CharField(max_length=128, db_index=True)
    syns = models.TextField()
    used = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return self.title
add_to_builtins('writer.game.templatetags.syns')
