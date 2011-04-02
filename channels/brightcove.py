import time
import cgi
import datetime
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass, STATUS_BAD, STATUS_GOOD, STATUS_UGLY
from utils import *
import httplib
import xbmcplugin
import xbmc

try:
    from pyamf import remoting
    has_pyamf = True
except ImportError:
    has_pyamf = False
    

    
class BrightcoveBaseChannel(BaseChannel):
    
    """
    None of this works. All videos stop playing after 1 minute.
    
    """
    is_abstract = True
    

    def get_swf_url(self):
        conn = httplib.HTTPConnection('c.brightcove.com')
        qsdata = dict(width=640, height=480, flashID=self.flash_experience_id, 
                      bgcolor="#000000", playerID=self.player_id, publisherID=self.publisher_id,
                      isSlim='true', wmode='opaque', optimizedContentLoad='true', autoStart='', debuggerID='')
        qsdata['@videoPlayer'] = self.video_id
        logging.debug("SWFURL: %s" % (urllib.urlencode(qsdata),))
        conn.request("GET", "/services/viewer/federated_f9?&" + urllib.urlencode(qsdata))
        resp = conn.getresponse()
        location = resp.getheader('location')
        base = location.split("?",1)[0]
        location = base.replace("BrightcoveBootloader.swf", "connection/ExternalConnection_2.swf")
        self.swf_url = location
        
    def get_clip_info(self, player_id, video_id):
        conn = httplib.HTTPConnection("c.brightcove.com")
        envelope = self.build_amf_request(player_id, video_id)
        conn.request("POST", "/services/amfgateway", str(remoting.encode(envelope).read()), {'content-type': 'application/x-amf'})
        response = conn.getresponse().read()
        response = remoting.decode(response).bodies[0][1].body[0]['data']['videoDTO']
        logging.debug(response)
        return response
   
    def choose_rendition(self, renditions):
        maxrate = int(self.plugin.get_setting("max_bitrate")) * 1024
        rends = [r for r in renditions if r['encodingRate'] < maxrate]
        if not rends:
            rends = renditions
        rends.sort(key=lambda r: r['encodingRate'])
        return rends[-1]
    
    def build_amf_request_body(self, player_id, video_id):
        return [
            player_id,
            {
                'optimizeFeaturedContent': 1, 
                'featuredLineupFetchInfo': {
                    'fetchLevelEnum': 4, 
                    'contentType': u'VideoLineup', 
                    'childLimit': 100
                }, 
                'lineupRefId': None, 
                'videoId': video_id, 
                'videoRefId': None, 
                'lineupId': None, 
                'fetchInfos': [
                    {'fetchLevelEnum': 1, 'contentType': u'VideoLineup', 'childLimit': 100}, 
                    {'grandchildLimit': 100, 'fetchLevelEnum': 3, 'contentType': u'VideoLineupList', 'childLimit': 100}
                ]
            }
        ]


    def build_amf_request(self, player_id, video_id):
        env = remoting.Envelope(amfVersion=0)
        env.bodies.append(
            (
                "/2", 
                remoting.Request(
                    target="com.brightcove.templating.TemplatingFacade.getContentForTemplateInstance", 
                    body=self.build_amf_request_body(player_id, video_id),
                    envelope=env
                )
            )
        )
        return env


    def find_ids(self, url):
        soup = get_soup(url)
        self.flash_experience_id = soup.find("object")['id']
        try:
            player_id = int(soup.find("object").find("param", {"name": "playerID"})['value'])
        except:
            player_id = None
            
        try:
            video_id = int(soup.find('object').find("param", {"name": "@videoPlayer"})['value'])
        except:
            video_id = None
        
        return player_id, video_id
    
    
        
        
class CPAC(BaseChannel):
    short_name = 'cpac'
    long_name = "CPAC"
    default_action = 'root'
    base_url = "http://www.cpac.ca/forms/"
    icon_path = 'cpac.jpg'
    
    def action_play_video(self):
        remote_url = self.base_url + self.args['remote_url']
        soup = get_soup(remote_url)
        obj = soup.find("object", {'id': "MPlayer2"})
        vidurl = obj.find('param', {'name': 'url'})['value']
        asx = get_soup(vidurl)
        entries = asx.findAll('entry')
        if len(entries) > 1:
            entries = entries[1:]
        
        if len(entries) > 1:
            self.plugin.get_dialog().ok("Error", "Too Many Entries to play")
            return None
        
        url = entries[0].ref['href']
        return self.plugin.set_stream_url(url)
        
    def action_list_episodes(self):
        soup = get_soup(self.base_url + self.args['remote_url'])
        for li in soup.find('div', {'id': 'video_scroll'}).findAll('div', {'class': 'list_item'}):
            links = li.findAll('a')
            ep_title = links[0].contents[0]
            show_title = links[1].contents[0]
            date_str = links[2].contents[0]
            self.plugin.add_list_item({
                'action': 'play_video',
                'channel': 'cpac',
                'remote_url': links[0]['href'],
                'Title': "%s (%s)" % (ep_title, date_str),
            }, is_folder=False)
            
            
        self.plugin.end_list()

    def action_list_shows(self):
        soup = get_soup(self.base_url)
        select = soup.find('select', {"name": 'proglinks'})
        for show in select.findAll('option')[1:]:
            data = {}
            data.update(self.args)
            data['action'] = 'list_episodes'
            data['remote_url'] = show['value'].split("|",1)[1]
            data['Title'] = show.contents[0]
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
    def action_latest_videos(self):
        url = self.base_url + "index.asp?dsp=template&act=view3&section_id=860&template_id=860&hl=e"
        soup = get_soup(url)
        for li in soup.find('div', {'id': 'video_scroll'}).findAll('div', {'class': 'list_item'}):
            links = li.findAll('a')
            ep_title = links[0].contents[0]
            show_title = links[1].contents[0]
            date_str = links[2].contents[0]
            logging.debug("VID: %s, %s" % (ep_title, show_title))
            self.plugin.add_list_item({
                'action': 'play_video',
                'channel': 'cpac',
                'remote_url': links[0]['href'],
                'Title': "%s - %s (%s)" % (show_title, ep_title, date_str),
            }, is_folder=False)
            
            
        self.plugin.end_list()
        
    def action_root(self):
        self.plugin.add_list_item({
            'action': 'latest_videos',
            'Title': 'Latest Videos',
            'channel': 'cpac',
        })
        self.plugin.add_list_item({
            'action': 'list_shows',
            'Title': 'All Shows',
            'channel': 'cpac',
        })
        self.plugin.end_list()
        
class Family(BaseChannel):
    status = STATUS_BAD
    short_name = 'family'
    long_name = 'Family.ca'
    base_url = 'http://www.family.ca'
    default_action = 'root'
    
    class FamilyURLParser(URLParser):
        def get_base_url(self):
            
            url = "%(scheme)s://%(netloc)s/%(app)s" % self.data
            if self.data['querystring']:
                url += "?%(querystring)s" % self.data
            return url
        
        def get_url_params(self):
            params = super(Family.FamilyURLParser, self).get_url_params()
            params.append(('pageUrl', 'http://www.family.ca/video/#video=%s' % (726,)))
            return params
    def action_play_video(self):
        qs = urldecode(get_page(self.base_url + "/video/scripts/loadToken.php").read().strip()[1:])['uri']
        filename = self.args['filename']
        url = "rtmpe://cp107996.edgefcs.net/ondemand/videos/family/%s?%s" % (filename, qs)
        parser = Family.FamilyURLParser(swf_url="http://www.family.ca/video/player.swf", playpath_qs=False)
        url = parser(url)
        self.plugin.set_stream_url(url)
        
    def action_browse_category(self):
        results = simplejson.load(get_page(self.base_url + "/video/scripts/loadGroupVideos.php?groupID=%s" % (self.args['id'],)))
        for vid in results['videosbygroup']:
            data = {}
            data.update(self.args)

            if vid['thumb']:
                thumb = self.base_url + "/video/images/thumbnails/%s" % (vid['thumb'],)
            else:
                thumb = ''
            data['Title'] = vid['title']
            data['Plot'] = vid['description']
            data['Thumb'] = thumb
            data['filename'] = vid['filename']
            data['action'] = 'play_video'
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
        
    def action_root(self):
        
        soup = get_soup(self.base_url + "/video/")
        div = soup.find('div', {'id': 'categoryList'})
        data = {}
        data.update(self.args)
        data['action'] = 'browse_featured'
        data['Title'] = 'Featured Videos'
        self.plugin.add_list_item(data)
        
        for a in div.findAll('a')[3:]:
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(a.contents[0].strip())
            data['action'] = 'browse_category'
            data['id'] = a['href'].split("(",1)[1].split(",")[0]
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
class CMT(BaseChannel):
    default_action = 'root'
    short_name = 'cmt'
    long_name = 'Country Music Television'
    cache_timeout = 60*15 #seconds
    
    def get_cached_page(self):
        cachedir = self.plugin.get_cache_dir()
        cachefilename = os.path.join(cachedir, 'cmt.cache')
        download = True
        if os.path.exists(cachefilename):
            try:
                data = simplejson.load(open(cachefilename))
                timestamp = data['cached_at'] 
                if time.time() - timestamp < self.cache_timeout:
                    download = False
                    data = data['html']
            except:
                pass
        
        if download:
            data = get_page("http://www.cmt.ca/musicvideos/").read()
            fh = open(cachefilename, 'w')
            simplejson.dump({'cached_at': time.time(), 'html': data}, fh)
            fh.close()
            
        return data
                    

    def action_play_video(self):
        url = "http://video.music.yahoo.com/up/fop/process/getPlaylistFOP.php?node_id=v" + self.args.get('video_id')
        page = get_page(url).read()
        soup = BeautifulStoneSoup(page)
        tag = soup.find('stream')
        url = tag['app']
        url += tag['fullpath']
        parse = URLParser(swf_url='http://d.yimg.com/cosmos.bcst.yahoo.com/up/fop/embedflv/swf/fop.swf')
        url = parse(url)
        return self.plugin.set_stream_url(url)
        
    def action_newest(self):
        soup = BeautifulSoup(self.get_cached_page())
        div = soup.find("div", {'id': 'Newest'})
        self.list_videos(div)
    
        
    def action_browse_genre(self):
        url = "http://www.cmt.ca/musicvideos/Category.aspx?id=%s" % (self.args['genre'],)
        soup = get_soup(url)
        div = soup.find("div", {'class': 'yahooCategory'})
        self.list_videos(div)
        
    def action_genres(self):
        soup = BeautifulSoup(self.get_cached_page())
        div = soup.find("div", {'id': 'Genre'})
        for tr in div.findAll('tr'):
            data = {}
            data.update(self.args)
            a = tr.find('a')
            try:
                data['Title'] = decode_htmlentities(a.contents[0].strip())
            except:
                continue
            data['action'] = 'browse_genre'
            data['genre'] = a['onclick'].rsplit("?",1)[1][:-1][3:]
            self.plugin.add_list_item(data)
        self.plugin.end_list()

            
            
    def list_videos(self, div):
        for li in div.findAll('li'):
            data = {}
            data.update(self.args)
            data['action'] = 'play_video'
            data['Thumb'] = li.find('img')['src']
            links = li.findAll('a')
            title, artist = links[1:]            
            data['video_id'] = re.search(r"videoId=v(\d+)", title['href']).groups()[0]
            title = title.contents[0].strip()
            artist = artist.contents[0].strip()
            
            data['Title'] = "%s - %s" % (artist, title)
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
        
    def action_search(self):
        page = self.get_cached_page()
        soup = BeautifulSoup(page)
        viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
        logging.debug("VIEWSTATE: %s" % (viewstate,))
        search_string = self.plugin.get_modal_keyboard_input("", "Enter a Full or Partial Artist Name")
        request = urllib2.Request(
            "http://www.cmt.ca/musicvideos/default.aspx", 
            urllib.urlencode({
                '__VIEWSTATE': viewstate,
                'in_txtSearch': search_string,
                'hd_activeTab': 0,
                'btnSearch.x': 0,
                'btnSearch.y': 0,
                '__SCROLLPOSITIONX': 0,
                '__SCROLLPOSITIONY': 0,
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
            })
        )
        logging.debug(request.data)
        page = urllib2.urlopen(request).read()
        soup = BeautifulSoup(page)
        
        div = soup.find("div", {'id': 'Artist'})
        logging.debug(div)
        self.list_videos(div)
        
    def action_most_popular(self):
        soup = BeautifulSoup(self.get_cached_page())
        div = soup.find("div", {'id': 'Popular'})
        self.list_videos(div)
        
        
    def action_root(self):
        data = {}
        data.update(self.args)

        data['Title'] = 'Most Popular Videos'
        data['action'] = 'most_popular'
        self.plugin.add_list_item(data)

        data['Title'] = 'Newest'
        data['action'] = 'newest'
        self.plugin.add_list_item(data)
        
        data['Title'] = 'Genres'
        data['action'] = 'genres'
        self.plugin.add_list_item(data)

        data['Title'] = 'Search'
        data['action'] = 'search'
        self.plugin.add_list_item(data)

        self.plugin.end_list()
        




class CityTVBaseChannel(BrightcoveBaseChannel):
    status = STATUS_BAD
    default_action = "list_shows"
    cache_timeout = 60*10
    is_abstract = True
    
    def action_play_episode(self):
        url = "http://video.citytv.com" + self.args['remote_url']
        player_id, video_id = self.find_ids(url)
        self.video_id = video_id
        self.player_id = player_id
        clipinfo = self.get_clip_info(player_id, video_id)
        logging.debug(clipinfo)
        self.publisher_id = clipinfo['publisherId']
        self.video_length = clipinfo['length']/1000
        self.get_swf_url()
        parser = URLParser(swf_url=self.swf_url, swf_verify=True)
        url = self.choose_rendition(clipinfo['renditions'])['defaultURL']
        url = parser(url)
        logging.debug("STREAM_URL: %s" % (url,))
        self.plugin.set_stream_url(url)
        
    def get_cached_page(self, remote_url):
        logging.debug(remote_url)        
        fname = urllib.quote_plus(remote_url)
        cdir = self.plugin.get_cache_dir()
        cachefilename = os.path.join(cdir, fname)
        download = True
        
        if os.path.exists(cachefilename):
            try:
                data = simplejson.load(open(cachefilename))
                timestamp = data['cached_at'] 
                if time.time() - timestamp < self.cache_timeout:
                    download = False
                    logging.debug("Using Cached Copy of: %s" % (remote_url,))
                    data = data['html']
            except:
                pass
        
        if download:
            data = get_page("http://video.citytv.com" + remote_url).read()
            try:
                fh = open(cachefilename, 'w')
                simplejson.dump({'cached_at': time.time(), 'html': data}, fh)
                fh.close()
            except:
                # failed to write cache file.
                # This happens due to a utf-8 decode error that's difficult to 
                # debug.  some pages won't be cached as a result.
                pass
            
        return data
        
    def action_browse_show(self):
        html = self.get_cached_page(self.args['remote_url'])
        soup = BeautifulSoup(html)
        toplevel = self.args.get('toplevel', None)
        section = self.args.get('section', None)
        if section:
            return self.browse_section()
        elif toplevel:
            return self.browse_toplevel()
        else:
            tabdiv = soup.find("div", {'class': re.compile(r'tabs.*')})
            toplevels = tabdiv.findAll("a")
            if len(toplevels) == 1:
                self.args['toplevel'] = toplevels[0].contents[0].strip()
                return self.browse_toplevel()
            else:
                for a in toplevels:
                    data = {}
                    data.update(self.args)
                    
                    data['Title'] = data['toplevel'] = a.contents[0].strip()
                    
                    self.plugin.add_list_item(data)
                self.plugin.end_list()
                
                

    def parse_episode_list(self, pages):
        monthnames = ["", "January", "February", "March", 
                      "April", "May", "June", "July", "August", 
                      "September", "October", "November", "December"]
        
        for page in pages:
            page = self.get_cached_page(page)
            soup = BeautifulSoup(page)
            div = soup.find('div', {'id': 'episodes'}).find('div', {'class': 'episodes'})
            for item in div.findAll('div', {'class': re.compile(r'item.*')}):
                data = {}
                data.update(self.args)
                data['action'] = 'play_episode'
                data['Plot'] = item.find('p').contents[0].strip()
                a = item.find('div', {'class': 'meta'}).h1.a
                try:
                    date_s = item.find('h5').contents[0].strip().replace("Aired on ","").strip()
                    m,d,y = date_s.split(" ")
                    m = monthnames.index(m)
                    d = d[:-1].strip()
                    y = y.strip()
                    data['Date'] = "%s.%s.%s" % (d,m,y)
                except:
                    pass
                
                data['Title'] = a.contents[0].strip()
                data['remote_url'] = a['href']
                data['Thumb'] = item.find('div', {'class': 'image'}).find('img')['src']
                yield data
        
    def parse_clip_list(self, pages):
        monthnames = ["", "January", "February", "March", 
                      "April", "May", "June", "July", "August", 
                      "September", "October", "November", "December"]
        
        for page in pages:
            page = self.get_cached_page(page)
            soup = BeautifulSoup(page)
            
            div = soup.find('div', {'id': 'clips'}).div.find('div', {'class': 'clips'})
            for epdiv in div.findAll('div', {'class': 'item'}):
                data = {}
                data.update(self.args)
                data['Thumb'] = epdiv.find('div', {"class": 'image'})['style'][23:-3]
                data['Title'] = epdiv.find('h1').find('a').contents[0].strip()
                data['action'] = 'play_episode'
                data['remote_url'] = epdiv.find('h1').find('a')['href']
                yield data
            

    def parse_show_list(self, pages):
        for page in pages:
            page = self.get_cached_page(page)
            soup = BeautifulSoup(page)
            div = soup.find("div", {'class': 'shows'})
            for item in div.findAll('div', {'class': 'item'}):
                a = item.find("h1").a
                data = {}
                data.update(self.args)
                data['action'] = 'browse_show'
                data['remote_url'] = a['href']
                data['Thumb'] = item.find("div", {'class': 'thumb'}).img['src']
                data['Title'] = decode_htmlentities(a.contents[0].strip())
                yield data
        
    def browse_section(self):
        page = self.get_cached_page(self.args['remote_url'])
        soup = BeautifulSoup(page)
        toplevel = self.args.get('toplevel')
        if toplevel == 'Full Episodes':
            div = soup.find("div", {'id': 'episodes'})
            parser = self.parse_episode_list
        elif toplevel == 'Video Clips':
            div = soup.find("div", {'id': 'clips'})
            parser = self.parse_clip_list
        paginator = div.find('ul', {'class': 'pagination'})
        pageas = paginator.findAll('a')
        pages = [self.args['remote_url']]
        pages += [a['href'] for a in pageas]
        items = parser(pages)
        for item in items:
            self.plugin.add_list_item(item, is_folder=False)
        self.plugin.end_list()
        
            
    def browse_toplevel(self):
        toplevel = self.args['toplevel']
        page = self.get_cached_page(self.args['remote_url'])
        soup = BeautifulSoup(page)
        if toplevel == 'Full Episodes':
            div = soup.find("div", {'id': 'episodes'})
        elif toplevel == 'Video Clips':
            div = soup.find("div", {'id': 'clips'})
        try:
            section_div = div.find('div', {'class': 'widget'}).find('div', {'class': 'middle'})
            sections = section_div.findAll('a')
        except:
            sections = []
        if not sections:
            return self.browse_section()
        elif len(sections) == 1:
            self.args['section'] = decode_htmlentities(sections[0].contents[0].strip())
            return self.browse_section()
        else:
            for section in sections:
                data = {}
                data.update(self.args)
                data['section'] = decode_htmlentities(section.contents[0].strip())
                data['remote_url'] = section['href']
                data['Title'] = data['section']
                self.plugin.add_list_item(data)
            self.plugin.end_list()

        

        
    def action_list_shows(self):
        
        page = self.get_cached_page(self.root_url)
        soup = BeautifulSoup(page)
        
        paginator = soup.find('ul', {'class': 'pagination'})
        pageas = paginator.findAll('a')
        pages = [self.root_url]
        pages += [a['href'] for a in pageas]
        for item in self.parse_show_list(pages):
            self.plugin.add_list_item(item)
        self.plugin.end_list()

       
        
class CityTV(CityTVBaseChannel):
    short_name = 'citytv'
    long_name = "CityTV"
    root_url = "/video/navigation.htm?N=0&type=shows&sort=Display"
    
class OLN(CityTVBaseChannel):
    short_name = 'oln'
    long_name = 'Outdoor Life Network'
    root_url = "/video/channel/oln/allmedia/4294965726/"
    
class G4TV(CityTVBaseChannel):
    short_name = 'g4'
    long_name = "G4 Tech TV"
    root_url = "/video/channel/g4/allmedia/4294965638/"
    
class Omni(CityTVBaseChannel):
    short_name = 'omni'
    long_name = 'OMNI TV'
    root_url = "/video/channel/omni/allmedia/4294965410/"

class ShortsInTheCity(CityTVBaseChannel):
    short_name = 'shortsinthecity'
    long_name = 'Shorts in the City'
    root_url = '/video/channel/shortsinthecity/allmedia/4294965731/'
    
    

class TVOKids(BrightcoveBaseChannel):
    
    short_name = 'tvokids'
    long_name = 'TVO Kids'
    default_action = 'root'
    base_url  = 'http://www.tvokids.com'
    player_id = 48543011001
    publisher_id = 15364602001
    flash_experience_id="null"

    def get_swf_url(self):
        conn = httplib.HTTPConnection('c.brightcove.com')
        qsdata = dict(width=640, height=480, flashID=self.flash_experience_id, 
                      bgcolor="#000000", playerID=self.player_id, publisherID=self.publisher_id,
                      isSlim='true', wmode='opaque', optimizedContentLoad='true', autoStart='', debuggerID='')
        qsdata['@videoPlayer'] = self.video_id
        logging.debug("SWFURL: %s" % (urllib.urlencode(qsdata),))
        conn.request("GET", "/services/viewer/federated_f9?&" + urllib.urlencode(qsdata))
        resp = conn.getresponse()
        location = resp.getheader('location')
        base = location.split("?",1)[0]
        location = base.replace("BrightcoveBootloader.swf", "federatedVideo/BrightcovePlayer.swf")
        self.swf_url = location
            
    def action_root(self):
        data = {}
        data.update(self.args)
        data['action'] = 'list_shows'
        data['age'] = 5
        data['Title'] = "Ages 2-5"
        self.plugin.add_list_item(data)
        data['Title'] = "Ages 11 and under"
        data['age'] = 11
        self.plugin.add_list_item(data)
        self.plugin.end_list()
        	
    def action_play_video(self):
        info = self.get_clip_info(self.player_id, self.args['bc_id'])
        self.video_id = self.args.get('bc_id')
        self.get_swf_url()
        logging.debug(self.swf_url)
        parser = URLParser(swf_url=self.swf_url, swf_verify=True)
        url = self.choose_rendition(info['renditions'])['defaultURL']
        app, playpath, wierdqs = url.split("&", 2)
        qs = "?videoId=%s&lineUpId=&pubId=%s&playerId=%s&affiliateId=" % (self.video_id, self.publisher_id, self.player_id)
        #playpath += "&" + wierdqs
        scheme,netloc = app.split("://")
        
        netloc, app = netloc.split("/",1)
        app = app.rstrip("/") + qs
        logging.debug("APP:%s" %(app,))
        tcurl = "%s://%s:1935/%s" % (scheme, netloc, app)
        logging.debug("TCURL:%s" % (tcurl,))
        #pageurl = 'http://www.tvokids.com/shows/worldofwonders'
        url = "%s tcUrl=%s app=%s playpath=%s%s swfUrl=%s conn=B:0 conn=S:%s&%s" % (tcurl,tcurl, app, playpath, qs, self.swf_url, playpath, wierdqs)
        logging.debug(url)
        self.plugin.set_stream_url(url)
        
        
    def action_browse_show(self):
        url = self.base_url + "/feeds/%s/all/videos_list.xml?random=%s" % (self.args['node_id'], int(time.time()), )
        page = get_page(url).read()
        soup = BeautifulStoneSoup(page)
        for node in soup.findAll('node'):
            data = {}
            logging.debug(node)
            data.update(self.args)
            data['action'] = 'play_video'
            data['Thumb'] = node.find('node_still').contents[0].strip()
            data['Title'] = decode_htmlentities(node.find('node_title').contents[0].strip())
            data['Plot'] = decode_htmlentities(node.find("node_short_description").contents[0].strip())
            data['bc_id'] = node.find("node_bc_id").contents[0].strip()
            data['bc_refid'] = node.find("node_bc_refid").contents[0].strip()
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list('episodes')
        
    def action_list_shows(self):
        age = int(self.args.get('age'))
        if age == 11:
            url = '/feeds/all/98/shows'
        elif age == 5:
            url = '/feeds/all/97/shows'
        page = get_page(self.base_url + url).read()
        soup = BeautifulStoneSoup(page)
        for node in soup.findAll('node'):
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(node.find('node_title').contents[0].strip())
            thumb = node.find('node_thumbnail').contents[0].strip()
            if not thumb.endswith(".swf"):
                data['Thumb'] = self.base_url + "/" + thumb
            data['node_id'] = node.find('node_id').contents[0].strip()
            data['action'] = 'browse_show'
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
            
            
class TVO(BrightcoveBaseChannel):
    status = STATUS_BAD
    short_name = 'tvo'
    long_name = 'TVO'
    default_action = 'list_shows'
    
    def action_browse_show(self):
        url = "http://www.tvo.org/TVOspecial4/WebObjects/BRIGHTCOVE.woa?htmlplaylisthomevp_%s" % (self.args.get('show'),)
        soup = get_soup(url)
        for item in soup.findAll('div', {'class': 'playlist_title'}):
            data = {}
            data.update(self.args)
            data['Thumb'] = item.find('img')['src']
            data['Title'] = decode_htmlentities(item.a.contents[0].strip())
            _date = decode_htmlentities(item.find('span', {'class': 'playlistInfoStats'}).contents[0]).split("|")[0].strip()
            m,d,y = _date.split("/")
            data['Date'] = "%s.%s.%s" % (d,m,y)
            data['Plot'] = decode_htmlentities(item.find('span', {'class': 'playlistShortDescription'}).contents[0].strip())
            data['action'] = 'play_video'
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list('episodes', [xbmcplugin.SORT_METHOD_LABEL, xbmcplugin.SORT_METHOD_DATE])
    
    def action_list_shows(self):
        soup = get_soup("http://www.tvo.org/TVO/WebObjects/TVO.woa?video")
        for a in soup.find("ul", {'id': 'playlistTabs'}).findAll('a'):
            logging.debug(a)
            data = {}
            data.update(self.args)
            data['action'] = 'browse_show'
            data['Title'] = decode_htmlentities(a.span.contents[0].strip())
            onclick = a['onclick'].rsplit("); ")[0][10:]
            playlist, pid, divid = onclick.split(",")
            playlist = playlist[1:-1]
            #divid = divid[1:-1]
            data['show'] = playlist
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
        
        
class AUX(BrightcoveBaseChannel):
    short_name = 'auxtv'
    long_name = "AUX.TV"
    status = STATUS_GOOD
    default_action = 'root'
    base_url = "http://www.aux.tv"
    cache_timeout = 60*20
    
    
    def get_cached_page(self, remote_url):
        fname = 'aux.tv.'+urllib.quote_plus(remote_url)
        cdir = self.plugin.get_cache_dir()
        cachefilename = os.path.join(cdir, fname)
        download = True
        
        if os.path.exists(cachefilename):
            try:
                data = simplejson.load(open(cachefilename))
                timestamp = data['cached_at'] 
                if time.time() - timestamp < self.cache_timeout:
                    download = False
                    data = data['html']
            except:
                pass
        
        if download:
            data = get_page(self.base_url + remote_url).read()
            try:
                fh = open(cachefilename, 'w')
                simplejson.dump({'cached_at': time.time(), 'html': data}, fh)
                fh.close()
            except:
                # failed to write cache file.
                # This happens due to a utf-8 decode error that's difficult to 
                # debug.  some pages won't be cached as a result.
                pass
            
        return data


    def get_swf_url(self):
        conn = httplib.HTTPConnection('c.brightcove.com')
        qsdata = dict(width=640, height=480, flashID=self.flash_experience_id, 
                      bgcolor="#000000", playerID=self.player_id, publisherID=self.publisher_id,
                      isSlim='true', wmode='opaque', optimizedContentLoad='true', autoStart='', debuggerID='')
        qsdata['@videoPlayer'] = self.video_id
        
        conn.request("GET", "/services/viewer/federated_f9?&" + urllib.urlencode(qsdata))
        resp = conn.getresponse()
        location = resp.getheader('location')
        base = location.split("?",1)[0]
        location = base.replace("BrightcoveBootloader.swf", "BrightcovePlayer.swf")
        self.swf_url = location
        
    def action_play_video(self):
        url = "http://www.aux.tv" + self.args['remote_url']
        player_id, video_id = self.find_ids(url)
        self.video_id = video_id
        self.player_id = player_id
        clipinfo = self.get_clip_info(player_id, video_id)
        self.publisher_id = clipinfo['publisherId']
        self.video_length = clipinfo['length']/1000
        self.get_swf_url()
        parser = URLParser(swf_url=self.swf_url, swf_verify=True)
        url = self.choose_rendition(clipinfo['renditions'])['defaultURL']
        app, playpath, wierdqs = url.split("&", 2)
        qs = "?videoId=%s&lineUpId=&pubId=%s&playerId=%s&affiliateId=" % (self.video_id, self.publisher_id, self.player_id)
        #playpath += "&" + wierdqs
        scheme,netloc = app.split("://")
        
        netloc, app = netloc.split("/",1)
        app = app.rstrip("/") + qs
        tcurl = "%s://%s:1935/%s" % (scheme, netloc, app)
        #pageurl = 'http://www.tvokids.com/shows/worldofwonders'
        url = "%s tcUrl=%s app=%s playpath=%s%s swfUrl=%s conn=B:0 conn=S:%s&%s" % (tcurl,tcurl, app, playpath, qs, self.swf_url, playpath, wierdqs)
        logging.debug(url)
        self.plugin.set_stream_url(url)
        
        
        
    def action_browse_show(self):
        rurl = self.args['remote_url']
        pagelinks = [rurl]
        soup = BeautifulSoup(self.get_cached_page(rurl))
        paginator = soup.find("div", {'id': 'videoPaginator'})
        if paginator:
            cell = paginator.find('td', {'align': 'center'})
            pagelinks += [rurl + a['href'] for a in cell.findAll('a')]
        logging.debug("PageLinks: %s" %(pagelinks,))
        for data in self.parse_episode_list(pagelinks):
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
    
    def parse_episode_list(self, pages):
        for page in pages:
            page = self.get_cached_page(page)
            soup = BeautifulSoup(page)            
            div = soup.find('div', {'id': 'fullVideoList'})
            for item in div.findAll('div', {'class': 'videoContainerWide'}):
                data = {}
                data.update(self.args)
                data['Thumb'] = item.find('img')['src']
                data['Title'] = decode_htmlentities(item.find('div', {'class': 'title'}).a.contents[0].strip())
                data['remote_url'] = item.find('div', {'class': 'title'}).a['href']
                data['action'] = 'play_video'
                yield data
        
                                                     
    def action_list_shows(self):
        page = self.get_cached_page('/shows/')
        soup = BeautifulSoup(page)
        #
        for div in soup.findAll('div', {'id': 'fullVideoList'}):
            div = div.div
            imdiv, datadiv = div.findAll("div", recursive=False)[:2]
            #logging.debug(imdiv, datadiv)
            data = {}
            data.update(self.args)
            data['Thumb'] = imdiv.find('img')['src']
            data['Title'] = decode_htmlentities(datadiv.find('a').contents[0].strip())
            data['action'] = 'browse_show'
            data['remote_url'] = datadiv.find('a')['href']
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
    def action_list_artists(self):
        section = self.args.get('Title')
        soup = BeautifulSoup(self.get_cached_page('/artists/'))
        section_divs = soup.findAll("div", {'class': 'pageSection clearfix'})
        if section == 'Featured Artists':
            div = section_divs[0]
        elif section == 'Popular Artists':
            div = section_divs[1]
        else:
            raise ChannelException("Unknown Artist Section")
        
        for artist in div.findAll("div", {'class': re.compile(r"peopleBox.*")}):
            adiv = artist.div.find('div', {'class': 'left'})
            data = {}
            data.update(self.args)
            data['Thumb'] = adiv.find('img')['src']
            link = adiv.find('div', {'class': 'titleBox'}).find('a')
            data['Title'] = decode_htmlentities(link.contents[0].strip())
            data['remote_url'] = link['href']
            self.plugin.add_list_item(data)
        self.plugin.end_list()
            

    def get_all_artists(self):
        cdir = self.plugin.get_cache_dir()
        cfile = os.path.join(cdir, 'aux.tv.all.artists.cache')
        if os.path.exists(cfile):
            try:
                startloadtime = time.time()
                fh = open(cfile,'r')
                data = simplejson.load(fh)
                fh.close()
                if time.time() - data['timestamp'] < 60*60*12: # 12h
                    logging.debug("SIMPLEJSON TOOK %s SECONDS" % (time.time() - startloadtime,))
                    return data['artists']
            except:
                raise
        
        import xbmcgui
        pdiag = xbmcgui.DialogProgress()
        pdiag.create("Updating Artist Cache")
        urls = ["/artists/"]
        soup = BeautifulSoup(self.get_cached_page(urls[0]))
        paginator = soup.find("div", {'id': "artistPaginator"})
        if paginator:
            cell = paginator.find("td", {'align': 'center'})
            lastpage = cell.findAll('a')[-1]
            lastpage = lastpage['href'].split("#",1)[0].split("=",1)[1]
            urls += ["/artists/?PAGEOFFSET=%s" % (p,) for p in range(1,int(lastpage))]

        artists = {}
        for i, url in enumerate(urls):
            if pdiag.iscanceled():
                return False
            pct = ((i+1) / float(len(urls))) * 100
            logging.debug("PCT:%s" % (pct,))
            pdiag.update(pct, "Fetching Page %s of %s" % (i+1, len(urls)))
            logging.debug("Fetching Artist Page %s of %s" % (i+1, len(urls)))
            soup = BeautifulSoup(self.get_cached_page(url))
            sec = soup.findAll("div", {'class': "pageSection clearfix"})[2]            
            for imgdiv in sec.findAll('div', {'class': 'pic'}):
                item = imgdiv.parent
                data = {'Title': decode_htmlentities(item.find('div', {'class': 'link'}).a.contents[0].strip()),
                        'Thumb': item.find('div', {'class': 'pic'}).find('img')['src'],
                        'remote_url': item.find('div', {'class': 'link'}).a['href']}
                key = data['Title'][0].upper()
                if key in "0123456789":
                    key = "#"
                if key in artists:
                    artists[key].append(data)
                else:
                    artists[key] = [data]
                
        pdiag.close()
        data = {'timestamp': time.time(), 'artists': artists}

        try:
            fh = open(cfile, 'w')
            simplejson.dump(data, fh)
            fh.close()
        except:
            raise
        return artists
    

    def action_artists_a_z_browse(self):
        let = self.args.get('Title')
        all_artists = self.get_all_artists()
        for artist in all_artists[let]:
            data = {}
            data.update(self.args)
            data.update(artist)
            data['action'] = 'browse_artist'
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
        
    def action_browse_artist(self):
        logging.debug(self.args.get('remote_url'))
        soup = BeautifulSoup(self.get_cached_page(self.args.get('remote_url')))
        pane = soup.find("div", {'id': 'homeUserVideosPane'})
        for item in pane.findAll('div', {'class': 'videoContainerVertical'}):
            data = {}
            data.update(self.args)
            data['action'] = 'play_artist_video'
            data['Thumb'] = item.find('img')['src']
            data['Title'] = decode_htmlentities(item.find('div', {'class': 'title'}).find('a').contents[0])
            data['video_id'] = item.find('div', {'class': 'title'}).find('a')['href'].rsplit(")",1)[0].split("(",1)[1]
            self.plugin.add_list_item(data, is_folder=False)
            
        self.plugin.end_list('episodes')
        
    def action_play_artist_video(self):
        url = "http://www.aux.tv" + self.args['remote_url']
        player_id, video_id = self.find_ids(url)
        self.video_id = video_id = self.args.get('video_id')
        self.player_id = player_id
        
        clipinfo = self.get_clip_info(player_id, video_id)
        self.publisher_id = clipinfo['publisherId']
        self.video_length = clipinfo['length']/1000
        self.get_swf_url()
        parser = URLParser(swf_url=self.swf_url, swf_verify=True)
        url = self.choose_rendition(clipinfo['renditions'])['defaultURL']
        app, playpath, wierdqs = url.split("&", 2)
        qs = "?videoId=%s&lineUpId=&pubId=%s&playerId=%s&affiliateId=" % (self.video_id, self.publisher_id, self.player_id)
        #playpath += "&" + wierdqs
        scheme,netloc = app.split("://")
        
        netloc, app = netloc.split("/",1)
        app = app.rstrip("/") + qs
        tcurl = "%s://%s:1935/%s" % (scheme, netloc, app)
        #pageurl = 'http://www.tvokids.com/shows/worldofwonders'
        url = "%s tcUrl=%s app=%s playpath=%s%s swfUrl=%s conn=B:0 conn=S:%s&%s" % (tcurl,tcurl, app, playpath, qs, self.swf_url, playpath, wierdqs)
        logging.debug(url)
        self.plugin.set_stream_url(url)
        
             
    def action_artists_a_z(self):
        data = {}
        data.update(self.args)
        data['action'] = 'artists_a_z_browse'
        for c in '#ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            data['Title'] = c
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
                 
    def action_root(self):
        root_items = [
            {'Title': 'Shows', 'action': 'list_shows'},
            {'Title': 'Featured Artists', 'action': 'list_artists'},
            {'Title': 'Popular Artists', 'action': 'list_artists'},
            {'Title': 'All Artists', 'action': 'artists_a_z'}
        ]
            
        for item in root_items:
            data = dict(self.args)
            data.update(item)
            
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        