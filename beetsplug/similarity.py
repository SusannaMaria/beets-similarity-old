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
import matplotlib.pyplot as plt
import networkx as nx
import os.path
from networkx.readwrite import json_graph
import json
import musicbrainzngs
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+
    from urllib.parse import quote_plus


try:
    import pygraphviz
    from networkx.drawing.nx_agraph import graphviz_layout
except ImportError:
    try:
        import pydotplus
        from networkx.drawing.nx_pydot import graphviz_layout
    except ImportError:
        raise ImportError("This example needs Graphviz and either "
                            "PyGraphviz or PyDotPlus")

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
        self._custom_labels = {}

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
                # create node for each similar artist
                self.get_similar(lib, depth, fullpath)
        else:
            self._log.info(u'Processing query ... this can take a while')
            # create node for each similar artist
            self.collect_artists(items)
            # create node for each similar artist
            self.get_similar(lib, depth, fullpath)
        #self.create_graphviz()
        self.create_graph(lib)
        self._log.info(u'Artist owned: {}', len(self._artistsOwned))
        self._log.info(u'Artist foreign: {}', len(self._artistsForeign))
        self._log.info(u'Relations: {}', len(self._relations))
        self._log.info(u'Nodes: {}', nx.classes.function.number_of_nodes(G))
        self._log.info(u'Edges: {}', nx.classes.function.number_of_edges(G))

        mbid = None
        for item in items:
            if item['mb_albumartistid']:
                mbid = item['mb_albumartistid']
                break
        if mbid:
            for nid, attrs in G.nodes(data=True):
                if attrs.get('mbid') == mbid :
                    nl_o = []
                    nl_f = []
                    print("Band:", G.nodes[nid]['myname'])
                    print("Owned:")
                    for neighbor_id in nx.classes.function.all_neighbors(G, nid):
                        name = G.nodes[neighbor_id]['myname']
                        if G.nodes[neighbor_id]['group']==0:
                            nl_f.append(G[nid][neighbor_id])
                        else:
                            nl_o.append(G[nid][neighbor_id])
                    for n in sorted( nl_o, key= lambda edge: edge['rate'],reverse=True ):
                        if nid == n['smbid']:
                            fid = n['tmbid']
                        else:
                            fid = n['smbid']

                        print("* {} {}".format(round(n['rate']),G.nodes[fid]['myname']))
                    print("Not owned:")
                    for n in sorted( nl_f, key= lambda edge: edge['rate'],reverse=True ):
                        if nid == n['smbid']:
                            fid = n['tmbid']
                        else:
                            fid = n['smbid']

                        print("* {} {}".format(round(n['rate']),G.nodes[fid]['lastfmurl']))
                    break


    def create_graphviz(self):
        """Create graph out of collected artists and relations."""
        plt.figure(figsize=(6,8))
        pos=graphviz_layout(G)
        nx.draw_networkx_nodes(G,pos,nodelist=G.nodes(),node_size=5, linewidths=0.1,vmin=0,vmax=1,alpha=0.8, node_color=[D[n] for n in G.nodes()])
        nx.draw_networkx_edges(G,pos,edgelist=G.edges(),width=0.1, edge_color="black",alpha=0.6)
        plt.axis('off')
        plt.tight_layout()
        plt.savefig("lanl_routes.png")

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
                artistnode['myname'] = item['albumartist']
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
                    self._log.debug(
                        u'collect: {}', artistnode)
                    self._artistsOwned.append(artistnode)
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
                    self._log.debug(u'Artist: {}-{}', artist['mbid'],
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
                            #print(valtmp)                            
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
                        #print("sim artists:",lastfmurl," ",mbid)

                        if name:
                            artistnode = ArtistNode(mbid, quote(name), lastfmurl)
                            if len(lib.items('artist:' + name)) > 0:
                                if ((artistnode not in
                                     self._artistsOwned) and
                                    (artistnode not in
                                     artistsshadow)):
                                    artistnode['group'] = 1
                                    artistnode['myname'] = name
                                    artistnode['owned'] = True

                                    artistsshadow.append(artistnode)
                                    self._log.info(u'I own this: {}', name)
                                    havechilds = True
                            else:
                                if artistnode not in self._artistsForeign:
                                    if not mbid:
                                        result = musicbrainzngs.search_artists(artist=name)

                                        for artist_mb in result['artist-list']:
                                            #print(u"{id}: {name}".format(id=artist_mb['id'], name=artist_mb["name"]))
                                            mbid=artist_mb['id']
                                            artistnode['mbid']=mbid
                                            break

                                    artistnode['group'] = 0
                                    artistnode['myname'] = name
                                    artistnode['owned'] = False
                                    self._artistsForeign.append(artistnode)

                            relation = Relation(artist['mbid'],
                                                mbid,
                                                artist['lastfmurl'],
                                                lastfmurl,
                                                artistinfo[1] * 1000)

                            # if relation not in _relations:
                            self._relations.append(relation)
                    

            self._artistsOwned.extend(artistsshadow)
            del artistsshadow[:]
            self.create_graph(lib)
            self.save_graph(fullpath)
            if not havechilds:
                break
            

    def save_graph(self, jsonfile):
        h = nx.relabel_nodes(G, self._custom_labels)

        data = json_graph.node_link_data(h)
        with open(jsonfile, 'w') as fp:
            json.dump(data, fp, indent=4, sort_keys=True)

    def create_graph(self, lib):
        """Create graph out of collected artists and relations."""
        G.clear()
        self._custom_labels = {}
        for owned_artist in self._artistsOwned:
            self._custom_labels[owned_artist['mbid']] = owned_artist['mbid']
            G.add_node(owned_artist['mbid'],
                       mbid=owned_artist['mbid'],
                       group=owned_artist['group'],
                       checked=owned_artist['checked'],
                       name=quote(owned_artist['name']),
                       lastfmurl=owned_artist['lastfmurl'],
                       myname=owned_artist['myname']
                       )
            
            self._log.debug(u'#{}', owned_artist['mbid'])

        for foreign_artist in self._artistsForeign:
            if foreign_artist not in self._artistsOwned:
                self._custom_labels[foreign_artist['mbid']] = foreign_artist['mbid']
                G.add_node(foreign_artist['mbid'],
                           mbid=foreign_artist['mbid'],
                           group=foreign_artist['group'],
                           checked=foreign_artist['checked'],
                           name=quote(foreign_artist['name']),
                           lastfmurl=foreign_artist['lastfmurl'],
                           myname=foreign_artist['myname'])
                self._log.debug(u'#{}', foreign_artist['mbid'])

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
