import csv
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass
from utils import *

class JSONCSVDialect(csv.Dialect):
    delimiter = ","
    skipinitalspace = True
    escapechar = "\\"
    quotechar = "'"
    doublequote = False
    lineterminator = "\n"
    quoting = csv.QUOTE_MINIMAL


class CBCBaseChannel(BaseChannel):
    is_abstract = True
    
    def parse_listing(self):
        pass
    
    

class CTVBaseChannel(BaseChannel):
    is_abstract = True
    root_url = 'VideoLibraryWithFrame.aspx'
    
    def action_play_clip(self):
        rurl = "http://esi.ctv.ca/datafeed/urlgenjs.aspx?vid=%s" % (self.args['ClipId'],)
        data = transform_stream_url(get_page(rurl).read().strip()[17:].split("'",1)[0], self.swf_url)
        url = data
        self.plugin.set_stream_url(url)
        
        
    def action_browse(self):
        rurl = self.get_url(self.args['remote_url'])
        div = get_soup(rurl).find('div', {'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = levelclass[5:]
        
        parser = getattr(self, 'parse_level_%s' % (levelclass,))
        
        
        for item in parser(div):
            if item.get('playable', False):
                logging.debug("Adding Playable Item")
                self.plugin.add_list_item(item, is_folder=False)
            else:
                self.plugin.add_list_item(item)
        self.plugin.end_list()
        
        
    def parse_level_4(self, soup):
        for li in soup.findAll('li'):
            a = li.find('dl', {"class": "Item"}).dt.a
            """
            return Playlist.GetInstance().Play(new Video( { EpisodeId: 70417,EpisodePermalink:'http://watch.ctv.ca/--my-dad-says/season-1/--my-dad-says-ep-118-whos-your-daddy/', Permalink:'http://watch.ctv.ca/--my-dad-says/season-1/--my-dad-says-ep-118-whos-your-daddy/#clip419519', IsAd:false, Thumbnail:'http://images.ctvdigital.com/images/pub2upload/3/2010_8_25/stuffmydadsays-400x300.jpg', EpisodeThumbnail:'http://images.ctvdigital.com/images/pub2upload/3/2010_8_25/stuffmydadsays-400x300.jpg', Rating:'', Description:'', Title:'$#*! My Dad Says : $#*! My Dad Says (Ep. 118) "Who\'s Your Daddy?" : $#*! My Dad Says (Ep. 118) "Who\'s Your Daddy?" Clip 1 of 4', Format:'FLV', ClipId:'419519', BugUrl: 'http://image01.ctvdigital.com/images/local/media/watermarks/CTV-Bug-256x144-v1-0.png' ,SiteMap:'$#*! My Dad Says (Ep. 118) "Who\'s Your Daddy?"||ShowId=8141&SeasonId=1852&EpisodeId=70417||Season 1||ShowId=8141&SeasonId=1852||$#*! My Dad Says||ShowId=8141', IsCanadaOnly:'1'} ), true, true  )
            """
            data = {}
            data.update(self.args)
            data.update(parse_bad_json(a['onclick'][45:-16]))
            data['channel'] = self.short_name
            data['action'] = 'play_clip'
            data['Rating'] = 0.0
            data['playable'] = True
            yield data
            
            
            
            
    def parse_level_3(self, soup):
        for li in soup.findAll('li'):
            a = li.find('a', {'id': re.compile(r'^Episode_\d+')})
            dl = li.find('dl')
            
            data = {}
            data.update(self.args)
            logging.debug("link: %s" % (a,))
            data.update({
                'Title': decode_htmlentities(a['title']),
                'channel': self.short_name,
            })
            try:
                data['Thumb'] = dl.find('dd', {'class': 'Thumbnail'}).find('img')['src']
            except:
                pass
            
            try:
                data['Plot'] = dl.find('dd', {'class': 'Description'}).contents[0]
            except:
                pass
                
                
            
            if "GetChildPanel('Show'" in a['onclick']:
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=2&ShowID=%s' % (a['id'],)
                data['ShowID'] = a['id']

            elif "GetChildPanel('Season'" in a['onclick']:
                showid = self.args['ShowID']
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=3&SeasonID=%s&ForceParentShowID=%s' % (a['id'], showid)
                data['ShowID'] = showid
                
            elif "GetChildPanel('Episode'" in a['onclick']:
                showid = self.args['ShowID']
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=3&ForceParentShowID=%s&EpisodeID=%s' % (showid, a['id'][8:])
                data['ShowID'] = showid
            
            yield data
    
    def parse_level_1(self, div):
        
        for a in div.findAll('a'):
            data = {}
            data.update(self.args)
            data.update({
                'Title': decode_htmlentities(a['title']),
                'channel': self.short_name,
            })
            
            if "GetChildPanel('Show'" in a['onclick']:
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=2&ShowID=%s' % (a['id'],)
                data['ShowID'] = a['id']

            elif "GetChildPanel('Season'" in a['onclick']:
                showid = self.args['ShowID']
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=3&SeasonID=%s&ForceParentShowID=%s' % (a['id'], showid)
                data['ShowID'] = showid
                
            elif "GetChildPanel('Episode'" in a['onclick']:
                showid = self.args['ShowID']
                data['action'] = 'browse'
                data['remote_url'] = 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=3&ForceParentShowID=%s&EpisodeID=%s' % (showid, a['id'][8:])
                data['ShowID'] = showid
                
                
            yield data
        
    
    
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
    swf_url = 'http://watch.ctv.ca/news/Flash/player.swf?themeURL=http://watch.ctv.ca/news/themes/CTVNews/player/theme.aspx',


class Discovery(CTVBaseChannel):
    short_name = 'discovery'
    base_url = 'http://watch.discoverychannel.ca/AJAX/'
    long_name = 'Discovery'
    swf_url = 'http://watch.discoverychannel.ca/Flash/player.swf?themeURL=http://watch.discoverychannel.ca/themes/Discoverynew/player/theme.aspx'
    
    
class ComedyNetwork(CTVBaseChannel):
    short_name = 'thecomedynetwork'
    base_url = 'http://watch.thecomedynetwork.ca/AJAX/'
    long_name = 'The Comedy Network'
    swf_url = 'http://watch.thecomedynetwork.ca/Flash/player.swf?themeURL=http://watch.thecomedynetwork.ca/themes/Comedy/player/theme.aspx'
        


class MuchMusic(CTVBaseChannel):
    short_name = 'muchmusic'
    long_name = 'Much Music'
    base_url = 'http://watch.muchmusic.com/AJAX/'
    swf_url = 'http://watch.muchmusic.com/Flash/player.swf?themeURL=http://watch.muchmusic.com/themes/MuchMusic/player/theme.aspx'
        

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
    base_url = 'watch.fashiontelevision.com'
    long_name = 'Fashion Television'
    swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'

class BravoFact(CTVBaseChannel):
    icon_path = 'bravofact.jpg'
    short_name = 'bravofact'
    base_url = 'http://watch.bravofact.com/AJAX/'
    long_name = 'Bravo Fact'
    swf_url = 'http://watch.bravofact.com/Flash/player.swf?themeURL=http://watch.bravofact.com/themes/BravoFact/player/theme.aspx'
        

    