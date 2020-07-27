# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Susanna Maria Hepp http://github.com/SusannaMaria
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,e
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

from __future__ import division, absolute_import, print_function

import pylast
from beets import ui
from beets import config
from beets import plugins
from beets.dbcore import types

import networkx as nx
import os.path
from networkx.readwrite import json_graph
import json


try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+
    from urllib.parse import quote_plus


LASTFM = pylast.LastFMNetwork(api_key=plugins.LASTFM_KEY)

PYLAST_EXCEPTIONS = (
    pylast.WSError,
    pylast.MalformedResponseError,
    pylast.NetworkError,
)

G = nx.Graph(program="https://github.com/beetbox/beets")


class SimilarityPlugin(plugins.BeetsPlugin):
    """Determine similarity of artists."""

    def __init__(self):
        """Class constructor, initialize things."""
        super(SimilarityPlugin, self).__init__()

        config['lastfm'].add({'user':     '',
                              'api_key':  plugins.LASTFM_KEY, })
        config['lastfm']['api_key'].redact = True

        self.config.add({'per_page': 500,
                         'retry_limit': 3,
                         'json': 'similarity.json',
                         'depth': 1,
                         'force': False, })
        self.item_types = {'play_count':  types.INTEGER, }

        self._artistsOwned = list()
        self._artistsForeign = list()
        self._relations = list()

    def commands(self):
        """Define the command of plugin and its options and arguments."""
        cmd = ui.Subcommand('similarity',
                            help=u'get similarity for artists')

        cmd.parser.add_option(
            u'-j', u'--json', dest='json',  metavar='FILE',
            action='store',
            help=u'read/write Graph as json-FILE.'
        )

        cmd.parser.add_option(
            u'-f', u'--force', dest='force',
            action='store_true', default=False,
            help=u're-fetch data when jsonfile already present'
        )

        cmd.parser.add_option(
            u'-d', u'--depth', dest='depth',
            action='store',
            help=u'How is the depth of searching.',
            type="int"
        )

        cmd.parser.add_option(
            u'-u', u'--update', dest='update',
            action='store_true', default=False,
            help=u'update data of jsonfile'
        )

        cmd.parser.add_option(
            u'-c', u'--convert', dest='convert',
            action='store_true', default=False,
            help=u'convert graph'
        )

        def func(lib, opts, args):

            self.config.set_args(opts)
            jsonfile = self.config['json'].as_str()
            force = self.config['force']
            update = self.config['update']
            convert = self.config['convert']
            if (self.config['depth']):
                depth = self.config['depth'].get(int)
            else:
                depth = 0
            items = lib.items(ui.decargs(args))

            self.import_similarity(lib, items, jsonfile,
                                   depth, force, update, convert)

        cmd.func = func
        return [cmd]

    def import_similarity(self, lib, items, jsonfile, depth, force, update, convert):
        """
        Import gml-file which contains similarity.

        Edges are similarity and Nodes are artists.
        """
        fullpath = os.path.join(config.config_dir(), jsonfile)
        self._log.info(u'{}', fullpath)
        if not force and os.path.isfile(fullpath) and os.access(fullpath,
                                                                os.R_OK):
            self._log.info(u'import of json file')
            self.import_graph(fullpath)

            if update:
                # create node for each similar artist
                self.collect_artists(items)
                self.create_graph(lib,fullpath)
                # create node for each similar artist
                self.get_similar(lib, depth, fullpath)
        else:
            self._log.info(u'Pocessing last.fm query')
            # create node for each similar artist
            self.collect_artists(items)
            # create node for each similar artist
            self.get_similar(lib, depth, fullpath)

        self._log.info(u'Artist owned: {}', len(self._artistsOwned))
        self._log.info(u'Artist foreign: {}', len(self._artistsForeign))
        self._log.info(u'Relations: {}', len(self._relations))

    def collect_artists(self, items):
        """Collect artists from query."""

        for item in items:
            if item['mb_albumartistid']:
                artistnode = ArtistNode(item['mb_albumartistid'],
                                        item['albumartist'],
                                        "",
                                        True)
                artistnode['group'] = 1
                artistnode['owned'] = True
                if artistnode not in self._artistsOwned:
                    lastfmurl = u''
                    try:

                        lastfm_artist = LASTFM.get_artist_by_mbid(
                            item['mb_albumartistid'])
                        lastfmurl = lastfm_artist.get_url()
                    except PYLAST_EXCEPTIONS as exc:
                        try:
                            lastfm_artist = LASTFM.get_artist(
                                quote(item['albumartist']))
                            lastfmurl = lastfm_artist.get_url()
                        except PYLAST_EXCEPTIONS as exc:
                            self._log.debug(u'1 last.fm error: {0}', exc)

                    artistnode['lastfmurl'] = lastfmurl
                    self._log.info(
                        u'collect: {}', artistnode)
                    self._artistsOwned.append(artistnode)

        #print("count {} {}".format(len(items),len(self._artistsOwned) ))
        return

    def get_similar(self, lib, depth, fullpath):
        """Collect artists from query."""
        depthcounter = 1

        while True:
            havechilds = False
            self._log.info(u'Level: {}-{}', depthcounter, depth)

            if not depth == 0 and depthcounter > depth:
                self._log.info(u'out!')
                break
            depthcounter += 1
            artistsshadow = list()
            for artist in self._artistsOwned:
                if not artist['checked']:
                    self._log.info(u'Artist: {}-{}', artist['mbid'],
                                   artist['lastfmurl'])
                    try:
                        lastfm_artist = LASTFM.get_artist_by_mbid(
                            artist['mbid'])
                    except PYLAST_EXCEPTIONS as exc:
                        try:
                            self._log.info(u'last.fm error: {0}', exc)

                            val=lib.items('mb_albumartistid:' + quote(artist['mbid']))
                            valtmp = val[0]['artist']
                            #valtmp = quote_plus(valtmp)
                            print(valtmp)                            
                            lastfm_artist = LASTFM.get_artist(valtmp)
                        except PYLAST_EXCEPTIONS as exc:
                            self._log.info(u'2 last.fm error: {0}', exc)
                            continue
                    try:
                        similar_artists = lastfm_artist.get_similar(10)
                        artist['checked'] = True
                    except pylast.WSError as exc:
                        similar_artists = []
                        artist['checked'] = False
                        self._log.info(u'2 last.fm error: {0}', exc)


                    for artistinfo in similar_artists:
                        mbid = artistinfo[0].get_mbid()
                        name = artistinfo[0].get_name()
                        lastfmurl = artistinfo[0].get_url()
                        print("sim artists:",lastfmurl)

                        if name:
                            artistnode = ArtistNode(mbid, quote(name), lastfmurl)
                            if len(lib.items('artist:' + quote(name))) > 0:
                                if ((artistnode not in
                                     self._artistsOwned) and
                                    (artistnode not in
                                     artistsshadow)):
                                    artistnode['group'] = 1
                                    artistsshadow.append(artistnode)
                                    self._log.info(u'I own this: {}', name)
                                    havechilds = True
                            else:
                                if artistnode not in self._artistsForeign:
                                    artistnode['group'] = 0
                                    self._artistsForeign.append(artistnode)

                            relation = Relation(artist['mbid'],
                                                mbid,
                                                artist['lastfmurl'],
                                                lastfmurl,
                                                artistinfo[1] * 1000)

                            # if relation not in _relations:
                            self._relations.append(relation)
                    self.create_graph(lib,fullpath)
            self._artistsOwned.extend(artistsshadow)
            del artistsshadow[:]
            if not havechilds:
                break

    def create_graph(self, lib, jsonfile):
        """Create graph out of collected artists and relations."""
        for relation in self._relations:
            G.add_edge(relation['source_mbid'],
                       relation['target_mbid'],
                       smbid=relation['source_mbid'],
                       tmbid=relation['target_mbid'],
                       slastfmurl=relation['source_lastfmurl'],
                       tlastfmurl=relation['target_lastfmurl'],
                       rate=relation['rate'],
                       )
            self._log.debug(u'{}#{}', relation['source_mbid'],
                            relation['target_mbid'])

        custom_labels = {}
        for owned_artist in self._artistsOwned:
            G.add_node(owned_artist['mbid'],
                       mbid=owned_artist['mbid'],
                       group=owned_artist['group'],
                       checked=owned_artist['checked'],
                       name=quote(owned_artist['name']),
                       lastfmurl=owned_artist['lastfmurl'],
                       myname=owned_artist['myname']
                       )
            custom_labels[owned_artist['mbid']] = owned_artist['mbid']
            self._log.debug(u'#{}', owned_artist['mbid'])

        for foreign_artist in self._artistsForeign:
            if foreign_artist not in self._artistsOwned:
                custom_labels[foreign_artist['mbid']] = foreign_artist['mbid']
                G.add_node(foreign_artist['mbid'],
                           mbid=foreign_artist['mbid'],
                           group=foreign_artist['group'],
                           checked=foreign_artist['checked'],
                           name=quote(foreign_artist['name']),
                           lastfmurl=foreign_artist['lastfmurl'],
                           myname=foreign_artist['myname'])
                self._log.debug(u'#{}', foreign_artist['mbid'])

        h = nx.relabel_nodes(G, custom_labels)

        data = json_graph.node_link_data(h)
        nx.write_gml(G, "test.gml")
        with open(jsonfile, 'w') as fp:
            json.dump(data, fp, indent=4, sort_keys=True)

    def import_graph(self, jsonfile):
        """Import graph from previous created gml file."""
        with open(jsonfile) as data_file:
            data = json.load(data_file)

        i = json_graph.node_link_graph(data)

        for artist in i.nodes(data=True):

            self._log.debug(u'{}', artist)
            if artist[1].get('mbid'):
                if artist[1]['group'] == 1:
                    artist[1]['owned'] = True
                else:
                    artist[1]['owned'] = False
                
                artistnode = ArtistNode(artist[1]['mbid'], artist[0],
                                        artist[1]['lastfmurl'],
                                        artist[1]['group'],
                                        artist[1]['owned'],
                                        artist[1]['checked'])
                artistnode['myname'] = artist[1]['myname']
                if artist[1]['myname']=="":
                    artistnode['myname'] = "unknown"
                   
                if artist[1]['group'] == 1:
                    if artistnode not in self._artistsOwned:
                        self._artistsOwned.append(artistnode)
                else:
                    if artistnode not in self._artistsForeign:
                        self._artistsForeign.append(artistnode)
        for relitem in i.edges(data=True):
            if not relitem[2]['tmbid']:
                relitem[2]['tmbid']=relitem[1]

            relation = Relation(relitem[2]['smbid'],
                                relitem[2]['tmbid'],
                                relitem[2]['slastfmurl'],
                                relitem[2]['tlastfmurl'],
                                relitem[2]['rate'])
            self._relations.append(relation)


class Relation():
    """Relations between Artists."""

    def __init__(self, source_mbid, target_mbid, source_lastfmurl,
                 target_lastfmurl, rate):
        """Constructor of class."""
        self.source_mbid = source_mbid
        self.target_mbid = target_mbid
        self.source_lastfmurl = source_lastfmurl
        self.target_lastfmurl = target_lastfmurl
        self.rate = rate

    def __eq__(self, other):
        """Override the default Equals behavior."""
        s = False
        t = False
        st = False

        if isinstance(other, self.__class__):

            if self.source_mbid and other.source_mbid:
                if self.source_mbid == other.source_mbid:
                    s = True
            else:
                if self.source_lastfmurl and other.source_lastfmurl:
                    if self.source_lastfmurl == other.source_lastfmurl:
                        s = True

            if self.target_mbid and other.target_mbid:
                if self.target_mbid == other.target_mbid:
                    t = True
            else:
                if self.target_lastfmurl and other.target_lastfmurl:
                    if self.target_lastfmurl == other.target_lastfmurl:
                        t = True

            if self.source_mbid and other.target_mbid:
                if self.source_mbid == other.target_mbid:
                    st = True
            else:
                if self.source_lastfmurl and other.target_lastfmurl:
                    if self.source_lastfmurl == other.target_lastfmurl:
                        st = True

            if self.target_mbid and other.source_mbid:
                if self.target_mbid == other.source_mbid:
                    st = True
            else:
                if self.target_lastfmurl and other.source_lastfmurl:
                    if self.target_lastfmurl == other.source_lastfmurl:
                        st = True

        if s and t or st:
            return True
        else:
            return False

    def __ne__(self, other):
        """Define a non-equality test."""
        if isinstance(other, self.__class__):
            return not self.__eq__(other)

    def __getitem__(self, key):
        """Define a getitem function."""
        if key == 'source_mbid':
            return self.source_mbid
        elif key == 'target_mbid':
            return self.target_mbid
        elif key == 'rate':
            return self.rate
        elif key == 'source_lastfmurl':
            return self.source_lastfmurl
        elif key == 'target_lastfmurl':
            return self.target_lastfmurl
        else:
            return None

    def tojson(self):
        """Define a setitem function."""
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)


class ArtistNode():
    """Artist Nodes."""

    mbid = u''
    name = u''
    lastfmurl = u''
    owned = False
    checked = False
    group = 0
    myname = u'unknown'

    def __init__(self, mbid, name, lastfmurl, group=0, owned=False,
                 checked=False):
        """Constructor of class."""
        self.mbid = mbid
        self.name = name
        self.owned = owned
        self.checked = checked
        self.group = group
        self.lastfmurl = lastfmurl

    def __eq__(self, other):
        """Override the default Equals behavior."""
        if isinstance(other, self.__class__):
            if self.mbid and other.mbid:
                return self.mbid == other.mbid
            elif self.lastfmurl and other.lastfmurl:
                return self.lastfmurl == other.lastfmurl
        return False

    def __ne__(self, other):
        """Define a non-equality test."""
        if isinstance(other, self.__class__):
            return not self.__eq__(other)

    def __getitem__(self, key):
        """Define a getitem function."""
        if key == 'mbid':
            return self.mbid
        elif key == 'name':
            return self.name
        elif key == 'owned':
            return self.owned
        elif key == 'checked':
            return self.checked
        elif key == 'group':
            return self.group
        elif key == 'lastfmurl':
            return self.lastfmurl
        elif key == 'myname':
            return self.myname            
        else:
            return None

    def __setitem__(self, key, value):
        """Define a setitem function."""
        if key == 'mbid':
            self.mbid = value
        elif key == 'name':
            self.name = value
        elif key == 'owned':
            self.owned = value
        elif key == 'checked':
            self.checked = value
        elif key == 'lastfmurl':
            self.lastfmurl = value
        elif key == 'group':
            self.group = value
        elif key == 'myname':
            self.myname = value

    def tojson(self):
        """Define a setitem function."""
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)

    def __str__(self):
        return(self.mbid + " " + self.name + " " + self.myname + " "+ str(self.owned) + " " + str(self.checked) + " " + str(self.group) + " " + self.lastfmurl)
