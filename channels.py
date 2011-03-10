import time
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass
from utils import *

class CBCBaseChannel(BaseChannel):
    is_abstract = True
    base_url = "http://cbc.feeds.theplatform.com/ps/JSON/PortalService/2.2/"

    PID = "_DyE_l_gC9yXF9BvDQ4XNfcCVLS4PQij"

    def get_root_url(self):
        return self.root_url % (self.PID,)

    def parse_callback(self, body):
        """
        Splits off Callback.Function.Name( .... ) and passes the remainder through
        to simplejson for decoding.

        """
        return simplejson.loads(body.split("(",1)[1].rsplit(")",1)[0]) ##can be removed if callback= parameter removed from querystring


    def get_categories(self, parent_id):
        """
        Returns a list of child-categories given a parent category id.
        """
        url = self.base_url + "getCategoryList?PID=%s&field=ID&field=title&field=parentID&field=description&field=customData&field=hasChildren&field=treeOrder&field=fullTitle&query=ParentIDs|%s&customField=backgroundImage&customField=Keywords&customField=IsDynamicPlaylist&customField=GroupLevel&customField=GroupOrder&customField=Account&customField=CreatedAfter&customField=CreatedBefore&customField=Genre&customField=Show&customField=SortField&customField=MaxClips&customField=SeasonNumber&customField=Sport&customField=Region&customField=Event&customField=People&customField=CBCPersonalities&customField=Aired&customField=AudioVideo&customField=BylineCredit&customField=Characters&customField=ClipType&customField=EpisodeNumber&customField=LiveOnDemand&customField=Organizations&customField=Producers&customField=Segment&customField=Sub-Event&customField=SortOrder&customField=AdCategory&&callback=CBC.APP.UberPlayer.onGetCategoriesByParentID" % (self.PID, parent_id)        
        data = self.parse_callback(get_page(url).read())
        cats = []
        for item in data['items']:
            cats.append({
                'Title': item['title'],
                'Description': item['description'],
                'HasChildren': item['hasChildren'],
                'FullTitle': item['fullTitle'],
                'remote_url': item['ID'],
                'channel': self.args['channel'],
                'action': 'browse',
            })
        return cats

    def get_releases(self, category_id):
        """
        Returns a list of videos in a given category

        """
        url = self.base_url + "getReleaseList?PID=%s&field=title&field=PID&field=ID&field=description&field=categoryIDs&field=thumbnailURL&field=URL&field=added&field=airdate&field=expirationDate&field=length&field=Keywords&contentCustomField=backgroundImage&contentCustomField=show&contentCustomField=relatedURL1&contentCustomField=relatedURL2&contentCustomField=relatedURL3&contentCustomField=sport&contentCustomField=seasonNumber&contentCustomField=clipType&contentCustomField=segment&contentCustomField=event&contentCustomField=adCategory&contentCustomField=LiveOnDemand&contentCustomField=AudioVideo&contentCustomField=EpisodeNumber&contentCustomField=RelatedClips&contentCustomField=Genre&contentCustomField=SubTitles&contentCustomField=CommentsEnabled&contentCustomField=CommentsExpirationDate&contentCustomField=adSite&query=CategoryIDs|%s&sortField=airdate&sortDescending=true&startIndex=1&endIndex=50&callback=CBC.APP.UberPlayer.onGetReleaseList" % (self.PID, category_id)
        data = self.parse_callback(get_page(url).read())
        rels = []
        for item in data['items']:
            rels.append({
                'Thumb': item['thumbnailURL'],
                'Title': item['title'],
                'Description': item['description'],
                'remote_url': item['ID'],
                'remote_PID': item['PID'],
                'channel': self.args['channel'],
                'action': 'browse_episode',
            })
        return rels

    def action_browse_episode(self):
        """
        Handles browsing the clips within an episode.

        """
        url = "http://release.theplatform.com/content.select?format=SMIL&mbr=true&pid=%s" % (self.args['remote_PID'],)
        soup = get_soup(url)
        logging.debug("SOUP: %s" % (soup,))
        base_url = decode_htmlentities(soup.meta['base'])
        try:
            base_url, qs = base_url.split("?",1)
        except ValueError:
            base_url = base_url
            qs = None


        for i, vidtag in enumerate(soup.findAll('video')):
            ref = vidtag.ref
            if ref is None:
                ref = vidtag
            clip_url = base_url + ref['src']

            if qs:
                clip_url = "?" + qs

            data = {}
            data.update(self.args)
            data['Title'] = self.args['Title'] + " clip %s" % (i+1,)
            data['remote_url'] = clip_url
            data['action'] = 'play'
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()

    def action_browse(self):
        """
        Handles the majority of the navigation.

        """
        # The remote_url is 
        # just a category id, not a full url.
        # Other channels plugins may choose to
        # pass the full remote_url to browse here.
        category_id = self.args['remote_url']


        categories = self.get_categories(category_id)
        releases = self.get_releases(category_id)

        for cat in categories:
            self.plugin.add_list_item(cat)

        for rel in releases:
            self.plugin.add_list_item(rel)
        self.plugin.end_list()


    def action_play(self):
        self.plugin.set_stream_url(transform_stream_url(self.args['remote_url'], self.swf_url))


    @classmethod
    def get_channel_entry_info(self):
        """
        This method is responsible for returning the info 
        used to generate the Channel listitem at the plugin's
        root level.

        """

        return {
            'Title': self.long_name,
            'Thumb': self.icon_path,
            'action': 'root',
            'remote_url': None,
            'channel': self.short_name,
        }


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
            data = {}
            data.update(self.args)
            data.update(parse_bad_json(a['onclick'][45:-16]))
            data['channel'] = self.short_name
            data['action'] = 'play_clip'
            data['Rating'] = 0.0 # the data in level4 already contains a rating. 
                                    # There was a crash which I THOUGHT was caused by 
                                    # the rating being a string instead of a float and
                                    # i'm not sure if it will crash or not if I remove it.
                                    # I'm making the comment extra large to remind myself
                                    # to check if its okay to remove.

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



class CanwestBaseChannel(CBCBaseChannel):
    is_abstract = True
    base_url = 'http://feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    root_url = None
    PID = None
    playerTag = None
    category_cache_timeout = 1 # value is in seconds. so 5 minutes.

    def get_root_url(self):
        url = self.base_url + 'getCategoryList?PID=%s'%(self.PID) + \
            '&field=ID&field=depth&field=title&field=hasReleases&field=fullTitle&field=thumbnailURL&field=hasChildren' + \
            '&query=CustomText|PlayerTag|%s'%(self.playerTag)
        logging.debug('get_root_url: %s'%url)
        return url

    def parse_callback(self, body):
        logging.debug('parse_callback body%s:' % body)
        return simplejson.loads(body)

    def get_cached_categories(self):
        fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.short_name,))
        try:
            if os.path.exists(fpath):
                data = simplejson.load(open(fpath))
                if data['cached_at'] + self.category_cache_timeout >= time.time():
                    logging.debug("Using Cached Categories")
                    return data['categories']
        except:
            return None
        return None


    def get_categories(self, parent_id=None):
        url = self.get_root_url()
        categories = self.get_cached_categories()
        if not categories:
            categories = self.parse_callback(get_page(url).read())['items']
            fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.short_name,))
            fh = open(fpath, 'w')
            simplejson.dump({'cached_at': time.time(), 'categories': categories}, fh)
            fh.close()

        if parent_id is None:
            categories = [c for c in categories if c['depth'] == 1 and (c['hasReleases'] or c['hasChildren'])]
        else:
            cat = [c for c in categories if c['ID'] == int(parent_id)][0]
            categories = [c for c in categories if c['fullTitle'].startswith(cat['fullTitle'] + "/") and c['depth'] == cat['depth'] + 1 and (c['hasReleases'] or c['hasChildren'])]

        cats = []
        for c in categories:
            logging.debug(c)
            data = {}
            data.update(self.args)
            data.update({
                'remote_url': c['ID'],
                'Title': c['title'],
                'action': 'browse',
            })
            cats.append(data)
        return cats

    def get_releases(self, category_id):
        url = self.base_url + 'getReleaseList?PID=%s'%(self.PID) + \
            '&field=title&field=PID&field=ID&field=description&field=categoryIDs&field=thumbnailURL&field=URL&field=airdate&field=length' + \
            '&sortField=airdate&sortDescending=true&startIndex=1&endIndex=50' + \
            '&query=CategoryIDs|%s'%(category_id)

        data = self.parse_callback(get_page(url).read())
        rels = []
        for item in data['items']:
            rels.append({
                'Thumb': item['thumbnailURL'],
                'Title': item['title'],
                'Description': item['description'],
                'remote_url': item['ID'],
                'remote_PID': item['PID'],
                'channel': self.args['channel'],
                'action': 'browse_episode',
            })
        return rels

    def action_browse_episode(self):
        #url = "http://release.theplatform.com/content.select?format=SMIL&mbr=true&pid=%s" % (self.args['remote_PID'],)
        url= 'http://release.theplatform.com/content.select?pid=%s&UserName=Unknown&Embedded=True&Portal=History&Tracking=True'%(self.args['remote_PID'],)
        logging.debug('action_browse_episode: url=%s'%url)
        soup = get_stone_soup(url)
        logging.debug("StoneSOUP: %s" % (soup,))

        """
        base_url = decode_htmlentities(soup.meta['base'])
        try:
            base_url, qs = base_url.split("?",1)
        except ValueError:
            base_url = base_url
            qs = None
        """

        #need to learn how to play with BeautifulStonSoup or... regex this mofo.
        #example: http://release.theplatform.com/content.select?pid=LIWB_K840fwnU_3_YC_U0WEps6m5tFQ0&UserName=Unknown&Embedded=True&Portal=History&Tracking=True
        for i, urltag in enumerate(soup.findAll(name='url')):
            logging.debug('i=%s, urltag=%s'%(i,urltag))
            clip_url = decode_htmlentities(urltag.contents[0])
            if clip_url.startswith("http://ad.ca.doubleclick"):
                logging.debug("Skipping Ad: %s" % (clip_url,))
                continue # skip ads

            qs = None
            playpath = None
            if '<break>' in clip_url:
                clip_url, playpath = clip_url.split("<break>",1)

            if "?" in clip_url:
                clip_url, qs = clip_url.split("?", 1)
            
            if playpath:
                clip_url += playpath
            
            if qs:
                clip_url += "?" + qs
            
                
            data = {}
            data.update(self.args)
            data['Title'] = self.args['Title']
            data['remote_url'] = clip_url
            data['action'] = 'play'
            self.plugin.add_list_item(data, is_folder=False)
            
        self.plugin.end_list()

    def action_browse(self):
        category_id = self.args['remote_url']
        categories = self.get_categories(category_id)
        logging.debug("Got %s Categories: %s" % (len(categories), "\n".join(repr(c) for c in categories)))
        releases = self.get_releases(category_id)
        logging.debug("Got %s Releases: %s" % (len(releases), "\n".join(repr(r) for r in releases)))

        for cat in categories:
            self.plugin.add_list_item(cat)
        for rel in releases:
            self.plugin.add_list_item(rel)
        self.plugin.end_list()


    def action_play(self):
        self.plugin.set_stream_url(transform_stream_url(self.args['remote_url'], self.swf_url))


    def action_root(self):
        categories = self.get_categories()
        for cat in categories:
            self.plugin.add_list_item(cat)
        self.plugin.end_list()

class GlobalTV(CanwestBaseChannel):
    short_name = 'global'
    long_name = 'Global TV'
    PID = 'W_qa_mi18Zxv8T8yFwmc8FIOolo_tp_g'
    playerTag = 'z/Global%20Video%20Centre' #urlencode
    #swf_url = 'http://www.globaltv.com/video/swf/flvPlayer.swf'

class HistoryTV(CanwestBaseChannel):
    short_name = 'history'
    long_name = 'History TV'
    PID = 'IX_AH1EK64oFyEbbwbGHX2Y_2A_ca8pk'
    playerTag = 'z/History%20Player%20-%20Video%20Center' #urlencode
    #swf_url = 'http://www.history.ca/video/cwp/swf/flvPlayer.swf'

class FoodNetwork(CanwestBaseChannel):
    short_name = 'foodnet'
    long_name = 'The Food Network'
    PID = '6yC6lGVHaVA8oWSm1F9PaIYc9tOTzDqY'
    playerTag = 'z/FOODNET%20Player%20-%20Video%20Centre' #urlencode
    #swf_url = 'http://webdata.globaltv.com/global/canwestPlayer/swf/4.1/flvPlayer.swf'

class HGTV(CanwestBaseChannel):
    short_name = 'hgtv'
    long_name = 'HGTV.ca'
    PID = 'HmHUZlCuIXO_ymAAPiwCpTCNZ3iIF1EG'
    playerTag = 'z/HGTV%20Player%20-%20Video%20Center' #urlencode
    #swf_url = 'http://www.hgtv.ca/includes/cwp/swf/flvPlayer.swf'


class Showcase(CanwestBaseChannel):
    short_name = 'showcase'
    long_name = 'Showcase'
    PID = 'sx9rVurvXUY4nOXBoB2_AdD1BionOoPy'
    playerTag = 'z/Showcase%20Video%20Centre' #urlencode
    #swf_url = 'http://www.showcase.ca/video/swf/flvPlayer.swf'
    

class SliceTV(CanwestBaseChannel):
    short_name = 'slice'
    long_name = 'Slice TV'
    PID = 'EJZUqE_dB8XeUUgiJBDE37WER48uEQCY'
    playerTag = 'z/Slice%20Player%20-%20New%20Video%20Center' #urlencode
    #swf_url = 'http://www.slice.ca/includes/cwp/swf/flvPlayer.swf'

class TVTropolis(CanwestBaseChannel):
    short_name = 'tvtropolis'
    long_name = 'TVtropolis'
    PID = '3i9zvO0c6HSlP7Fz848a0DvzBM0jUWcC'
    playerTag = 'z/TVTropolis%20Player%20-%20Video%20Center' #urlencode
    #swf_url = 'http://www.tvtropolis.com/swf/cwp/flvPlayer.swf'

class diyNet(CanwestBaseChannel):
    short_name = 'diynet'
    long_name = 'The DIY Network'
    PID = 'FgLJftQA35gBSx3kKPM46ZVvhP6JxTYt'
    playerTag = 'z/DIY%20Network%20-%20Video%20Centre' #urlencode
    #swf_url = 'http://www.diy.ca/Includes/cwp/swf/flvPlayer.swf'

    
class CBC(CBCBaseChannel):
    short_name = 'cbc'
    long_name = 'CBC'
    base_url = 'http://cbc.feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    root_url = "getCategoryList?PID=%s&field=fullTitle&field=treeOrder&field=hasChildren&field=customData&field=description&field=parentID&field=title&field=ID&customField=AdCategory&customField=SortOrder&customField=Sub-Event&customField=Segment&customField=Producers&customField=Organizations&customField=LiveOnDemand&customField=EpisodeNumber&customField=ClipType&customField=Characters&customField=BylineCredit&customField=AudioVideo&customField=Aired&customField=CBCPersonalities&customField=People&customField=Event&customField=Region&customField=Sport&customField=SeasonNumber&customField=MaxClips&customField=SortField&customField=Show&customField=Genre&customField=CreatedBefore&customField=CreatedAfter&customField=Account&customField=GroupOrder&customField=GroupLevel&customField=IsDynamicPlaylist&customField=Keywords&customField=backgroundImage&query=FullTitles|News&callback=CBC.APP.UberPlayer.onGetCategoriesByTitle&callback=CBC.APP.UberPlayer.onGetCategoriesByParentID"
    PID = "_DyE_l_gC9yXF9BvDQ4XNfcCVLS4PQij"

    def action_root(self):

        self.plugin.add_list_item({
            'channel': 'cbc',
            'Title': "Television",
            'action': 'browse',
            'remote_url': "1221254309"
        })
        self.plugin.add_list_item({
            'channel': 'cbc',
            'Title': "News",
            'action': 'browse',
            'remote_url': "1221258968"
        })
        self.plugin.add_list_item({
            'channel': 'cbc',
            'Title': "Sports",
            'action': 'browse',
            'remote_url': "1221284063" 
        })
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
    swf_url = 'http://watch.ctv.ca/news/Flash/player.swf?themeURL=http://watch.ctv.ca/news/themes/CTVNews/player/theme.aspx',


class Discovery(CTVBaseChannel):
    short_name = 'discovery'
    base_url = 'http://watch.discoverychannel.ca/AJAX/'
    long_name = 'Discovery'
    swf_url = 'http://watch.discoverychannel.ca/Flash/player.swf?themeURL=http://watch.discoverychannel.ca/themes/Discoverynew/player/theme.aspx'


class ComedyNetwork(CTVBaseChannel):
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
    base_url = 'http://watch.fashiontelevision.com/AJAX/'
    long_name = 'Fashion Television'
    swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'


class BravoFact(CTVBaseChannel):
    icon_path = 'bravofact.jpg'
    long_name = 'Bravo Fact'
    short_name = 'bravofact'
    base_url = 'http://watch.bravofact.com/AJAX/'
    swf_url = 'http://watch.bravofact.com/Flash/player.swf?themeURL=http://watch.bravofact.com/themes/BravoFact/player/theme.aspx'

