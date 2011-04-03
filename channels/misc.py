import time
import cgi
import datetime
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass, STATUS_BAD, STATUS_GOOD, STATUS_UGLY
from utils import *
import httplib
import xbmcplugin
import xbmc
from channel import *

class CPAC(BaseChannel):
    short_name = 'cpac'
    long_name = "CPAC"
    default_action = 'root'
    base_url = "http://www.cpac.ca/forms/"
    icon_path = 'cpac.jpg'
    
    def action_play_video(self):
        remote_url = self.base_url + self.args['remote_url']
        soup = BeautifulSoup(self.plugin.fetch(remote_url, max_age=self.cache_timeout))
        obj = soup.find("object", {'id': "MPlayer2"})
        vidurl = obj.find('param', {'name': 'url'})['value']
        asx = BeautifulSoup(self.plugin.fetch(vidurl, max_age=self.cache_timeout))
        entries = asx.findAll('entry')
        if len(entries) > 1:
            entries = entries[1:]
        
        if len(entries) > 1:
            self.plugin.get_dialog().ok("Error", "Too Many Entries to play")
            return None
        
        url = entries[0].ref['href']
        return self.plugin.set_stream_url(url)
        
    def action_list_episodes(self):
        soup = BeautifulSoup(self.plugin.fetch(self.base_url + self.args['remote_url'], max_age=self.cache_timeout))
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
        soup = BeautifulSoup(self.plugin.fetch(self.base_url, max_age=self.cache_timeout))
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
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
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
        qs = urldecode(self.plugin.fetch(self.base_url + "/video/scripts/loadToken.php").read().strip()[1:])['uri']
        filename = self.args['filename']
        url = "rtmpe://cp107996.edgefcs.net/ondemand/videos/family/%s?%s" % (filename, qs)
        parser = Family.FamilyURLParser(swf_url="http://www.family.ca/video/player.swf", playpath_qs=False)
        url = parser(url)
        self.plugin.set_stream_url(url)
        
    def action_browse_category(self):
        results = simplejson.load(self.plugin.fetch(self.base_url + "/video/scripts/loadGroupVideos.php?groupID=%s" % (self.args['id'],), max_age=self.cache_timeout))
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
        
        soup = BeautifulSoup(self.plugin.fetch(self.base_url + "/video/", max_age=self.cache_timeout))
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
                    

    def action_play_video(self):
        url = "http://video.music.yahoo.com/up/fop/process/getPlaylistFOP.php?node_id=v" + self.args.get('video_id')
        page = self.plugin.fetch(url).read()
        soup = BeautifulStoneSoup(page)
        tag = soup.find('stream')
        url = tag['app']
        url += tag['fullpath']
        parse = URLParser(swf_url='http://d.yimg.com/cosmos.bcst.yahoo.com/up/fop/embedflv/swf/fop.swf')
        url = parse(url)
        return self.plugin.set_stream_url(url)
        
    def action_newest(self):
        soup = BeautifulSoup(self.plugin.fetch("http://www.cmt.ca/musicvideos/",max_age=self.cache_timeout))
        div = soup.find("div", {'id': 'Newest'})
        self.list_videos(div)
    
        
    def action_browse_genre(self):
        url = "http://www.cmt.ca/musicvideos/Category.aspx?id=%s" % (self.args['genre'],)
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        div = soup.find("div", {'class': 'yahooCategory'})
        self.list_videos(div)
        
    def action_genres(self):
        soup = BeautifulSoup(self.plugin.fetch("http://www.cmt.ca/musicvideos/",max_age=self.cache_timeout))
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
        soup = BeautifulSoup(self.plugin.fetch("http://www.cmt.ca/musicvideos/",max_age=self.cache_timeout))
        
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
        soup = BeautifulSoup(self.plugin.fetch("http://www.cmt.ca/musicvideos/",max_age=self.cache_timeout))
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
        




