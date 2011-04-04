from theplatform import *

try:
    from pyamf import remoting
    has_pyamf = True
except ImportError:
    has_pyamf = False
    
try:
    from sqlite3 import dbapi2 as sqlite
    
except:
    from pysqlite2 import dbapi2 as sqlite

class CTVBaseChannel(BaseChannel):
    status = STATUS_GOOD
    is_abstract = True
    root_url = 'VideoLibraryWithFrame.aspx'
    default_action = 'root'
    
    def action_root(self):
        url = self.base_url + self.root_url
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        ul = soup.find('div', {'id': 'Level1'}).find('ul')
        for li in ul.findAll('li'):
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(li.a['title'])
            data['action'] = 'browse_show'
            data['show_id'] = li.a['id']
            self.plugin.add_list_item(data)
        self.plugin.end_list()

    def action_browse(self):
        """
        DEPRECATED Bookmarks Shouldn't Use this..
        need to find a way to update user's bookmarks
        
        """
        rurl = self.args.get('remote_url', 'None')
        if rurl == 'None' or rurl is None:
            return self.action_root()
        
        logging.debug("RURL: %s" %(rurl.__class__,))
        show_id = re.findall(r"\&ShowID=(\d+)", rurl)
        if show_id:
            self.args['show_id'] = show_id[0]
            return self.action_browse_show()
        
        season_id = re.findall(r"\&SeasonID=(\d+)", rurl)
        if season_id:
            self.args['season_id'] = season_id[0]
            return self.action_browse_season()
        
        episode_id = re.findall(r"&EpisodeID=(\d+)", rurl)
        if episode_id:
            self.args['episode_id'] = eposode_id[0]
            return self.action_browse_episode()
            
        
    def action_browse_season(self):
        url = "http://esi.ctv.ca/datafeed/pubsetservice.aspx?sid=" + self.args['season_id']
        page = self.plugin.fetch(url, max_age=self.cache_timeout).read()
        soup = BeautifulStoneSoup(page)
        for ep in soup.overdrive.gateway.contents:
            if not ep.playlist.contents:
                continue
            data = {}
            data.update(self.args)
            data['Title'] = ep.meta.headline.contents[0].strip()
            data['Plot'] = ep.meta.subhead.contents[0].strip()
            m,d,y = ep['pubdate'].split("/")
            data['Date'] = "%s.%s.%s" % (d,m,y)
            try:
                data['Thumb'] = ep.meta.image.contents[0].strip()
            except:
                pass
            
            data['videocount'] = ep['videocount']
            vc = int(ep['videocount'])
            if vc == 1:
                action = 'play_episode'
            elif vc <= int(self.plugin.get_setting('max_playlist_size')) \
                 and self.plugin.get_setting("make_playlists") == "true":
                action = 'play_episode'
            else:
                action = 'browse_episode'
            data['action'] = action
            data['episode_id'] = ep['id']
            self.plugin.add_list_item(data, is_folder=vc != 1)
        self.plugin.end_list('episodes', [xbmcplugin.SORT_METHOD_DATE, xbmcplugin.SORT_METHOD_LABEL])
        
    def action_play_episode(self):
        import xbmc
        vidcount = self.args.get('videocount')
        if vidcount:
            vidcount = int(vidcount)
        
        if vidcount  and vidcount == 1:
            data = list(self.iter_clip_list())[0]
            logging.debug(data)
            url = self.clipid_to_stream_url(data['clip_id'])
            return self.plugin.set_stream_url(url, data)
        else:
            playlist = xbmc.PlayList(1)
            playlist.clear()
            for clipdata in self.iter_clip_list():
                url = self.plugin.get_url(clipdata)
                li = self.plugin.add_list_item(clipdata, is_folder=False, return_only=True)
                ok = playlist.add(url, li)
                logging.debug("CLIPDATA: %s, %s, %s, %s" % (clipdata, url, li, ok))
            
            time.sleep(1)
            logging.debug("CLIPDATA: %s" % (playlist,))
            xbmc.Player().play(playlist)
            xbmc.executebuiltin('XBMC.ActivateWindow(fullscreenvideo)')
            self.plugin.end_list()

    def iter_clip_list(self):
        url = "http://esi.ctv.ca/datafeed/content.aspx?cid=" + self.args['episode_id']
        soup = BeautifulStoneSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        
        plot = soup.find('content').meta.subhead.contents[0].strip()
                             
        for el in soup.find('playlist').findAll('element'):
            data = {}
            data.update(self.args)
            data['action'] = 'play_clip'
            data['Title'] = el.title.contents[0].strip()
            data['Plot'] = plot
            data['clip_id'] = el['id']
            yield data
            
    def action_browse_episode(self):
        logging.debug("ID: %s" % (self.args['episode_id'],))
        for data in self.iter_clip_list():
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
        
        
    def action_browse_show(self):
        url = self.base_url + 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=2&ShowID=%s' % (self.args['show_id'],)
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        div = soup.find('div',{'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = int(levelclass[5:])
        if levelclass == 4:
            # Sites like TSN Always return level4 after the top level
            for li in soup.findAll('li'):
                a = li.find('dl', {"class": "Item"}).dt.a
                data = {}
                data.update(self.args)
                data.update(parse_bad_json(a['onclick'][45:-16]))
                data['action'] = 'play_clip'
                data['clip_id'] = data['ClipId']
                self.plugin.add_list_item(data, is_folder=False)
            self.plugin.end_list()
        
        else:
            for li in soup.find('ul').findAll('li'):
                a = li.find('a')
                is_folder = True
                data = {}
                data.update(self.args)
                if "Interface.GetChildPanel('Season'" in a['onclick']:
                    data['action'] = 'browse_season'
                    data['season_id'] = a['id']
                elif "Interface.GetChildPanel('Episode'" in a['onclick']:
                    data['action'] = 'browse_episode'
                    if self.plugin.get_setting("make_playlists") == "true":
                        data['action'] = 'play_episode'
                    data['episode_id'] = a['id'][8:]
                data['Title'] = decode_htmlentities(a['title'])
                self.plugin.add_list_item(data)
            self.plugin.end_list()
        
    def clipid_to_stream_url(self, clipid):
        rurl = "http://esi.ctv.ca/datafeed/urlgenjs.aspx?vid=%s" % (clipid)
        parse = URLParser(swf_url=self.swf_url, force_rtmp=not self.plugin.get_setting("awesome_librtmp") == "true")        
        url = parse(self.plugin.fetch(rurl).read().strip()[17:].split("'",1)[0])
        return url
    
    def action_play_clip(self):
        url = self.clipid_to_stream_url(self.args['clip_id'])
        logging.debug("Playing Stream: %s" % (url,))
        self.plugin.set_stream_url(url)
        


class CTVLocalNews(CTVBaseChannel):
    short_name = 'ctvlocal'
    long_name = 'CTV Local News'
    default_action = 'root'
    
    local_channels = [
        ('British Columbia', 'ctvbc.ctv.ca'),
        ('Calgary', 'calgary.ctv.ca'),
        ('Edmonton', 'edmonton.ctv.ca'),
        ('Montreal', 'montreal.ctv.ca'),
        ('Northern Ontario', 'northernontario.ctv.ca'),
        ('Ottawa', 'ottawa.ctv.ca'),
        ('Regina', 'regina.ctv.ca'),
        ('Saskatoon', 'saskatoon.ctv.ca'),
        ('Southwestern Ontario', 'swo.ctv.ca'),
        ('Toronto', 'toronto.ctv.ca'),
        ('Winnipeg', 'winnipeg.ctv.ca'),
    ]

        
    def action_root(self):
        for channel, domain in self.local_channels:
            self.plugin.add_list_item({
                'Title': channel, 
                'action': 'browse',
                'channel': self.short_name, 
                'entry_id': None,
                'local_channel': channel,
                'remote_url': domain,

                'Thumb': self.args['Thumb'],
            })
        self.plugin.end_list()

        
    def action_browse(self):
        soup = BeautifulSoup(self.plugin.fetch("http://%s/" % (self.args['remote_url'],), max_age=self.cache_timeout))
        for script in soup.findAll('script'):
            try:
                txt = script.contents[0].strip()
            except:
                continue
            
            if txt.startswith("VideoPlaying["):
                txt = txt.split("{",1)[1].rsplit("}")[0]
                
                data = {}
                data.update(self.args)
                data.update(parse_javascript_object(txt))
                data.update({
                    'action': 'play_clip',
                    'remote_url': data['ClipId'],
                    'clip_id': data['ClipId']
                })
                self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
        
class CTV(CTVBaseChannel):
    short_name = 'ctv'
    long_name = 'CTV'
    base_url = 'http://watch.ctv.ca/AJAX/'
    swf_url = 'http://watch.ctv.ca/Flash/player.swf?themeURL=http://watch.ctv.ca/themes/CTV/player/theme.aspx'


class TSN(CTVBaseChannel):
    short_name = 'tsn'
    long_name = 'The Sports Network'
    base_url = 'http://watch.tsn.ca/AJAX/'    
    swf_url = 'http://watch.tsn.ca/Flash/player.swf?themeURL=http://watch.ctv.ca/themes/TSN/player/theme.aspx'


class CTVNews(CTVBaseChannel):    
    base_url = 'http://watch.ctv.ca/news/AJAX/'
    short_name = 'ctvnews'
    long_name = 'CTV News'
    swf_url = 'http://watch.ctv.ca/news/Flash/player.swf?themeURL=http://watch.ctv.ca/news/themes/CTVNews/player/theme.aspx'


class Discovery(CTVBaseChannel):
    short_name = 'discovery'
    base_url = 'http://watch.discoverychannel.ca/AJAX/'
    long_name = 'Discovery'
    swf_url = 'http://watch.discoverychannel.ca/Flash/player.swf?themeURL=http://watch.discoverychannel.ca/themes/Discoverynew/player/theme.aspx'


class ComedyNetwork(CTVBaseChannel):
    status = STATUS_UGLY
    short_name = 'comedynetwork'
    base_url = 'http://watch.thecomedynetwork.ca/AJAX/'
    long_name = 'The Comedy Network'
    swf_url = 'http://watch.thecomedynetwork.ca/Flash/player.swf?themeURL=http://watch.thecomedynetwork.ca/themes/Comedy/player/theme.aspx'



class Space(CTVBaseChannel):
    short_name = 'space'
    long_name = "Space" 
    base_url = "http://watch.spacecast.com/AJAX/"
    swf_url = "http://watch.spacecast.com/Flash/player.swf?themeURL=http://watch.spacecast.com/themes/Space/player/theme.aspx"





class MuchMusic(CTVBaseChannel):
    status = STATUS_BAD
    short_name = 'muchmusic'
    long_name = 'Much Music'
    base_url = 'http://watch.muchmusic.com/AJAX/'
    swf_url = 'http://watch.muchmusic.com/Flash/player.swf?themeURL=http://watch.muchmusic.com/themes/MuchMusic/player/theme.aspx'
    jukebox_db_update_interval = 60*60*24 # 1 day

    def jukebox_db_check(self):
        dbfile = os.path.join(xbmc.translatePath('special://profile/addon_data/plugin.video.canada.on.demand/'), 'MMJukebox.db')
        self.jukebox_db_conn = sqlite.connect(dbfile)
        curs = self.jukebox_db_conn.cursor()
        curs.execute("""create table if not exists jukebox_meta (
            key text primary key on conflict replace,
            value text
        )""")
        
        curs.execute("""create table if not exists artists (
            id integer primary key on conflict ignore,
            name text,
            rank integer null
            
        )""")
        
        curs.execute("""create table if not exists videos (
            id integer primary key on conflict ignore,
            artist_id integer,
            title text,
            last_played integer,
            FOREIGN KEY(artist_id) REFERENCES artists(id)
        )""")
        self.jukebox_db_conn.commit()
        curs.close()
        curs = self.jukebox_db_conn.cursor()
        curs.execute("select count(*) from artists;")
        count = curs.fetchall()[0][0]
        curs.close()
        if count == 0:
            return self.jukebox_update_db()
            
        curs = self.jukebox_db_conn.cursor()
        curs.execute("""select key, value from jukebox_meta where key = 'last_updated'""")
        results = curs.fetchall()
        curs.close()
        if len(results) == 0 or time.time() - int(results[0][1]) > self.jukebox_db_update_interval:
            return self.jukebox_update_db()
            
            
    def jukebox_get_artist_videos(self, artist_id):
        url="http://esi.ctv.ca/datafeed/content.aspx?cid=%s" % (artist_id,)
        soup = BeautifulStoneSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        for item in soup.findAll('element'):
            yield item

            
    def jukebox_update_db(self):
        import xbmcgui        
        progress = xbmcgui.DialogProgress()
        progress.create("Updating Muchmusic Jukebox DB")
        soup = BeautifulSoup(self.plugin.fetch("http://watch.muchmusic.com/AJAX/VideoLibraryContents.aspx?GetChildOnly=true&PanelID=2&ShowID=1707", max_age=self.cache_timeout))
        pages = []
        curs = self.jukebox_db_conn.cursor()
        tot = float(len(soup.findAll('a')))
        pct = 0
        for i, letter in enumerate(soup.findAll("a")):
            if progress.iscanceled():
                self.jukebox_db_conn.commit()
                curs.close()
                return
            url = "http://esi.ctv.ca/datafeed/pubsetservice.aspx?sid=" + letter['id']
            progress.update(pct, "Fetching Artists - %s" % (letter.contents[0].strip(),), "")
            soup = BeautifulStoneSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
            pct = int(((i+1) / tot) * 100)

            for artist in soup.gateway.findAll('content'):
                artistname = decode_htmlentities(artist.meta.headline.contents[0].strip())
                curs.execute("""insert into artists (id, name) values (?, ?)""", (artist['id'], artistname))
                for video in self.jukebox_get_artist_videos(artist['id']):
                    videoname = decode_htmlentities(video.title.contents[0].strip())
                    curs.execute("""insert into videos (id, artist_id, title) VALUES (?, ?, ?)""", (video['id'], 
                                                                                                    artist['id'],
                                                                                                    videoname
                                                                                                    )
                                 )
                    progress.update(pct, artistname, videoname)
                    if progress.iscanceled():
                        self.jukebox_db_conn.commit()
                        curs.close()
                        return
        curs.execute("""insert into jukebox_meta (key, value) VALUES('last_updated',?)""", (int(time.time()),))
        curs.close()
        self.jukebox_db_conn.commit()
        player = JukeboxPlayer()
        

    
        
    def action_jukebox_root(self):
        self.jukebox_db_check()
        playlist = xbmc.PlayList(1)
        playlist.clear()
        curs = self.jukebox_db_conn.cursor()
        curs.execute("""select id, title from videos order by random() limit 5""")
        for row in curs.fetchall():
            data = {'action': 'play_clip', 'clip_id': row[0], 'jukebox':1, 'Title': row[1], 'channel': "muchmusic"}        
            li = self.plugin.add_list_item(data, is_folder=False, return_only=True)
            url = self.plugin.get_url(data)
            playlist.add(url,li)
        
        xbmc.Player(1).play(playlist)
        self.plugin.end_list()
        
        

    def action_play_clip(self):
        import cgi
        self.jukebox_db_check()
        url = self.clipid_to_stream_url(self.args['clip_id'])
        logging.debug("Playing Stream: %s" % (url,))
        if self.args.get('jukebox'):
            playlist = xbmc.PlayList(1)
            pos = playlist.getposition()
            logging.debug("CURRENT POS: %s" % (pos,))
            items = []
            if pos >= 1:
                for x in range(pos,len(playlist)):
                    pli = playlist[x]
                    data = dict(cgi.parse_qsl(pli.getfilename().split("?",1)[1]))
                    
                    _li = self.plugin.add_list_item(data, is_folder=False, return_only=True)
                    logging.debug(data)
                    _url = pli.getfilename()
                    items.append((_url, _li))
                playlist.clear()
                for item in items:
                    playlist.add(item[0], item[1])
                    
                logging.debug("ITEMS: %s" % (items,))
            if len(playlist) < 5:
                dbfile = os.path.join(xbmc.translatePath('special://profile/addon_data/plugin.video.canada.on.demand/'), 'MMJukebox.db')
                self.jukebox_db_conn = sqlite.connect(dbfile)                
                curs = self.jukebox_db_conn.cursor()
                curs.execute("select id, title from videos order by random() limit 5")
                for row in curs.fetchall():
                    data = {'action': 'play_clip', 'clip_id': row[0], 'jukebox':1, 'Title': row[1], 'channel': "muchmusic"}        
                    li = self.plugin.add_list_item(data, is_folder=False, return_only=True)
                    url = self.plugin.get_url(data)
                    playlist.add(url,li)

        self.plugin.set_stream_url(url)
        
    def action_root(self):
        url = self.base_url + self.root_url
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        ul = soup.find('div', {'id': 'Level1'}).find('ul')
        data= {}
        data.update(self.args)
        data['action'] = 'jukebox_root'
        data['Title'] = '[Jukebox (experimental)]'
        data['Thumb'] = self.plugin.get_resource_path('images', 'Wurlitzer.png')
        self.plugin.add_list_item(data, is_folder=True)
        for li in ul.findAll('li'):
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(li.a['title'])
            data['action'] = 'browse_show'
            data['show_id'] = li.a['id']
            self.plugin.add_list_item(data)
        self.plugin.end_list()


class Bravo(CTVBaseChannel):
    short_name = 'bravo'
    long_name = "Bravo!"
    base_url = 'http://watch.bravo.ca/AJAX/'
    swf_url = 'http://watch.bravo.ca/Flash/player.swf?themeURL=http://watch.bravo.ca/themes/CTV/player/theme.aspx'


class BNN(CTVBaseChannel):
    base_url = 'http://watch.bnn.ca/AJAX/'
    long_name = 'Business News Network'
    short_name = 'bnn'
    swf_url = 'http://watch.bnn.ca/news/Flash/player.swf?themeURL=http://watch.bnn.ca/themes/BusinessNews/player/theme.aspx'



class Fashion(CTVBaseChannel):
    short_name = 'fashion'
    base_url = 'http://watch.fashiontelevision.com/AJAX/'
    long_name = 'Fashion Television'
    swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'


class BravoFact(CTVBaseChannel):
    long_name = 'Bravo Fact'
    short_name = 'bravofact'
    base_url = 'http://watch.bravofact.com/AJAX/'
    swf_url = 'http://watch.bravofact.com/Flash/player.swf?themeURL=http://watch.bravofact.com/themes/BravoFact/player/theme.aspx'
  
