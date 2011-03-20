import time
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass, STATUS_BAD, STATUS_GOOD, STATUS_UGLY
from utils import *

class ThePlatformBaseChannel(BaseChannel):
    is_abstract = True
    base_url = None
    PID = None
    category_cache_timeout = 60 # value is in seconds. so 5 minutes.

    def get_categories_json(self):
        return self.base_url + 'getCategoryList?PID=%s'%(self.PID) + \
            '&field=ID&field=depth&field=title&field=description&field=hasReleases&field=fullTitle&field=thumbnailURL&field=hasChildren'

    def get_releases_json(self):
        return self.base_url + 'getReleaseList?PID=%s'%(self.PID) + \
            '&field=title&field=PID&field=ID&field=description&field=categoryIDs&field=thumbnailURL&field=URL&field=airdate&field=length&field=bitrate' + \
            '&sortField=airdate&sortDescending=true&startIndex=1&endIndex=100'



    def parse_callback(self, body):
        logging.debug('parse_callback body %s:' % body)
        return simplejson.loads(body)


    def get_cache_key(self):
        return self.short_name
    
    def get_cached_categories(self, parent_id):
        
        categories = None

        fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.get_cache_key(),))
        try:
            if os.path.exists(fpath):
                data = simplejson.load(open(fpath))
                if data['cached_at'] + self.category_cache_timeout >= time.time():
                    logging.debug("using cached Categories")
                    categories = data['categories']
        except:
            logging.debug("no cached Categories path")

        if not categories:
            logging.debug('http-retrieving categories')
            url = self.get_categories_json(parent_id)
            logging.debug('get_cached_categories(p_id=%s) url=%s'%(parent_id, url))
        
            categories = self.parse_callback(get_page(url).read())['items']
            if self.category_cache_timeout > 0:
                fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.short_name,))
                fh = open(fpath, 'w')
                simplejson.dump({'cached_at': time.time(), 'categories': categories}, fh)
                fh.close()

        return categories

    
    def get_categories(self, parent_id=None):

        categories = self.get_cached_categories(parent_id)

        #needs to be defined by sub-class:
        #  - CBC does an actual drill-down on parentId
        #  - Canwest uses string-matching on the fullTitle field
        categories = self.get_child_categories(categories, parent_id)
            
        cats = []
        for c in categories:
            #logging.debug(c)
            data = {}
            data.update(self.args)
            data.update({
                'entry_id': c['ID'],
                'Thumb': c['thumbnailURL'],
                'Title': c['title'],
                'Plot': c['description'],
                'action': 'browse',
                'force_cache_update': False,
            })
            
            #cbc-only, so check if key is present on other providers (Canwest)
            if 'customData' in c:
                for dict in c['customData']:
                    if dict['value']:
                        #if dict['value'] == '(not specified)':
                            #dict['value'] = "''"
                        #if dict['value'] != '':
                        data.update({dict['title']: dict['value']},) #urlquoteval(dict['value'])
                
            cats.append(data)
            
        logging.debug("get_categories cats=%s"%cats)
        return cats


    def get_releases(self, parameter): #category_id for Canwest, a customData dict for CBC 
        logging.debug('get_releases (parameter=%s)'%parameter)
        
        url = self.get_releases_json(parameter) #has a %s in it--  Canwest:a real cat_id, CBC: the customTags, 
        logging.debug('get_releases url=%s'%url)
        
        data = self.parse_callback(get_page(url).read())
        
        rels = []
        for item in data['items']:
#            logging.debug(item)
            if item['bitrate'] != '':
                title = '%s (%d kbps)'%(item['title'],int(item['bitrate'])/1024)
            else:
                title = item['title']
            action = 'browse_episode'
            if self.plugin.get_setting('make_playlists') == 'true':
                action = 'play_episode'
            rels.append({
                'Thumb': item['thumbnailURL'],
                'Title': title,
                'Plot': item['description'],
                'entry_id': item['ID'],
                'remote_url': item['URL'],
                'remote_PID': item['PID'],
                'channel': self.args['channel'],
                'action': action
            })
        return rels


    def action_root(self):
        logging.debug('ThePlatformBaseChannel::action_root')
        parent_id = self.args['entry_id'] # this should be None from @classmethod
        if parent_id == 'None':
            parent_id = None
        categories = self.get_categories(parent_id)# and root=true
        for cat in categories:
            self.plugin.add_list_item(cat)
        self.plugin.end_list()


    def action_browse(self):
        """
        Handles the majority of the navigation.

        """
        parent_id = self.args['entry_id']

        categories = self.get_categories(parent_id)
        logging.debug("Got %s Categories: %s" % (len(categories), "\n".join(repr(c) for c in categories)))
        releases = self.get_releases(self.args)
        logging.debug("Got %s Releases: %s" % (len(releases), "\n".join(repr(r) for r in releases)))

        for cat in categories:
            self.plugin.add_list_item(cat)
        for rel in releases:
            self.plugin.add_list_item(rel)
        self.plugin.end_list()


    def get_episode_list_data(self, remote_pid):
        url = 'http://release.theplatform.com/content.select?&pid=%s&format=SMIL&mbr=true' % (remote_pid,)
        soup = get_soup(url)
        logging.debug("SOUP: %s" % (soup,))
        results = []

        for i, ref in enumerate(soup.findAll('ref')):
            base_url = ''
            playpath = None

            if ref['src'].startswith('rtmp://'): #all other channels type of SMIL
            #the meta base="http:// is actually the prefix to an adserver
                try:
                    base_url, playpath = decode_htmlentities(ref['src']).split('<break>', 1) #<break>
                except ValueError:
                    base_url = decode_htmlentities(ref['src'])
                    playpath = None
                logging.debug('all other channels type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            else:
                if soup.meta['base'].startswith('rtmp://'): #CBC type of SMIL
                    base_url = decode_htmlentities(soup.meta['base'])
                    playpath = ref['src']
                    logging.debug('CBC type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
                else:
                    continue

            qs = None
            try:
                base_url, qs = base_url.split("?",1)
            except ValueError:
                base_url = base_url

            logging.debug({'base_url': base_url, 'playpath': playpath, 'qs': qs, })

            clip_url = base_url
            if playpath:
                clip_url += playpath
            if qs:
                clip_url += "?" + qs

            data = {}
            data.update(self.args)
            data['Title'] = self.args['Title']# + " clip %s" % (i+1,)
            data['clip_url'] = clip_url
            data['action'] = 'play'
            results.append(data)
        return results
    
    def action_play_episode(self):
        import xbmc
        playlist = xbmc.PlayList(1)
        playlist.clear() 
        for data in self.get_episode_list_data(self.args['remote_PID']):
            url = self.plugin.get_url(data)
            item = self.plugin.add_list_item(data, is_folder=False, return_only=True)
            playlist.add(url, item)
        xbmc.Player().play(playlist)
        xbmc.executebuiltin('XBMC.ActivateWindow(fullscreenvideo)')

        
    def action_browse_episode(self):
        for item in self.get_episode_list_data(self.args['remote_PID']):
            self.plugin.add_list_item(item, is_folder=False)
        self.plugin.end_list()


    def action_play(self):
        parse = URLParser(swf_url=self.swf_url)
        self.plugin.set_stream_url(parse(self.args['clip_url']))


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
            'entry_id': None,
            'channel': self.short_name,
            'force_cache_update': True,
            'use_rtmp': 0,
        }



class CTVBaseChannel(BaseChannel):
    status = STATUS_GOOD
    is_abstract = True
    root_url = 'VideoLibraryWithFrame.aspx'
    
    def action_play_clip(self):
        rurl = "http://esi.ctv.ca/datafeed/urlgenjs.aspx?vid=%s" % (self.args['ClipId'],)
        parse = URLParser(swf_url=self.swf_url, force_rtmp=self.args.get('use_rtmp', ''))
        url = parse(get_page(rurl).read().strip()[17:].split("'",1)[0])
        logging.debug("Playing Stream: %s" % (url,))
        self.plugin.set_stream_url(url)



    def action_play_episode(self):
        import xbmc
        rurl = self.get_url(self.args['remote_url'])
        div = get_soup(rurl).find('div', {'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = levelclass[5:]
        if levelclass != '4': # Browsing at the clip level
            raise ChannelException("An error occured trying to play a full episode,try turning off the 'Automatically Play All Clips' setting")
        
        parser = getattr(self, 'parse_level_%s' % (levelclass,))
        playlist = xbmc.PlayList(1)
        playlist.clear()
        
        for item in parser(div):
            if item.get('playable', False):
                if self.args.get('use_rtmp'):
                    logging.debug("Adding Forced RTMP Item")
                else:
                    logging.debug("Adding Playable Item: title=%s"%item['Title'])
                url = self.plugin.get_url(item)
                li = self.plugin.add_list_item(item, is_folder=False, return_only=True)
                playlist.add(url, li)
        xbmc.Player().play(playlist)
        xbmc.executebuiltin('XBMC.ActivateWindow(fullscreenvideo)')

    def action_browse(self):
        rurl = self.get_url(self.args['remote_url'])
        div = get_soup(rurl).find('div', {'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = levelclass[5:]
        if levelclass == '4': # Browsing at the clip level
                              # We want to build a context menu
                              # Item to allow 're-browsing' this directory
                              # with forced rtmp urls.
            menu_args = {}
            menu_args.update(self.args)

            if self.args.get('use_rtmp'):
                menu_args['use_rtmp'] = ''
                menuitem = ('Use Given Urls', 'Container.Update(%s)' % (self.plugin.get_url(menu_args)))
            else:
                menu_args['use_rtmp'] = 1
                menuitem = ('Force RTMP Urls', 'Container.Update(%s)' % (self.plugin.get_url(menu_args)))
            
            context_menu_items = [menuitem]
        else:
            context_menu_items = None
        
        parser = getattr(self, 'parse_level_%s' % (levelclass,))

        for item in parser(div):
            if item.get('playable', False):
                if self.args.get('use_rtmp'):
                    logging.debug("Adding Forced RTMP Item")
                else:
                    logging.debug("Adding Playable Item: title=%s"%item['Title'])
                self.plugin.add_list_item(item, is_folder=False, context_menu_items=context_menu_items)
            else:
                self.plugin.add_list_item(item)
        self.plugin.end_list()


    def parse_level_4(self, soup):
        for li in soup.findAll('li'):
            logging.debug(li)
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
        episode_action = 'browse'
        if self.plugin.get_setting('make_playlists') == 'true':
            episode_action = 'play_episode'
            
        for li in soup.findAll('li'):
            a = li.find('a', {'id': re.compile(r'^Episode_\d+')})
            dl = li.find('dl')

            data = {}
            data.update(self.args)
            
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
                data['action'] = episode_action 
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



class CanwestBaseChannel(ThePlatformBaseChannel):
    is_abstract = True
    base_url = 'http://feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    PID = None
    root_depth = 1

    def get_categories_json(self,arg=None):
        return ThePlatformBaseChannel.get_categories_json(self) # + '&query=ParentIDs|%s'%arg

    def get_releases_json(self,arg='0'):
        return ThePlatformBaseChannel.get_releases_json(self) + '&query=CategoryIDs|%s'% (self.args['entry_id'],)

    def children_with_releases(self, categorylist, cat):
        
        if cat['fullTitle'] == '':
            prefix = ''
        else:
            prefix = cat['fullTitle'] + "/"
        
        children = [c for c in categorylist \
                    if c['depth'] == cat['depth'] + 1 \
                    and c['fullTitle'].startswith(prefix) \
                    and (c['hasReleases'] or self.children_with_releases(categorylist, c))]
        return children
            
        
    def get_child_categories(self, categorylist, parent_id):
        
        show_empty = self.plugin.get_setting('show_empty_cat') == 'true'
        if parent_id is None:
            if self.root_depth > 0:
                cat = [c for c in categorylist if c['depth'] == self.root_depth - 1][0]
            else:
                cat = {'depth': -1, 'fullTitle': ''}
        else:
            logging.debug("ParentID: %s [%s]" % (parent_id, type(parent_id)))
            cat = [c for c in categorylist if c['ID'] == int(parent_id)][0]
        
        if cat['fullTitle'] == '':
            prefix = ''
        else:
            prefix = cat['fullTitle'] + "/"
        
        if show_empty:
            categories = [c for c in categorylist if c['depth'] == cat['depth'] + 1 \
                          and c['fullTitle'].startswith(prefix)]
            
        else:
            categories = self.children_with_releases(categorylist, cat)

        return categories


    #override ThePlatFormbase so ?querystring isn't included in playpath 
    #this could be temp-only, actually. paypath doesn't seem to care about extra parameters
    def action_play(self):
        parse = URLParser(swf_url=self.swf_url, playpath_qs=False)
        self.plugin.set_stream_url(parse(self.args['clip_url']))



class GlobalTV(CanwestBaseChannel):
    short_name = 'global'
    long_name = 'Global TV'
    PID = 'W_qa_mi18Zxv8T8yFwmc8FIOolo_tp_g'
    #swf_url = 'http://www.globaltv.com/video/swf/flvPlayer.swf'

    
    def get_categories_json(self,arg=None):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/Global%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url

class GlobalNews(CanwestBaseChannel):
    short_name = 'globalnews'
    long_name = 'Global News'
    PID = 'M3FYkz1jcJIVtzmoB4e_ZQfqBdpZSFNM'
    local_channels = [
        ('Global News','z/Global%20News%20Player%20-%20Main'),
        ('Global National','z/Global%20Player%20-%20The%20National%20VC'),
        ('BC', 'z/Global%20BC%20Player%20-%20Video%20Center'),
        ('Calgary', 'z/Global%20CGY%20Player%20-%20Video%20Center'),
        ('Edmonton', 'z/Global%20EDM%20Player%20-%20Video%20Center'),
        ('Lethbridge', 'z/Global%20LTH%20Player%20-%20Video%20Center'),
        ('Maritimes', 'z/Global%20MAR%20Player%20-%20Video%20Center'),
        ('Montreal', 'z/Global%20QC%20Player%20-%20Video%20Center'),
        ('Regina', 'z/Global%20REG%20Player%20-%20Video%20Center'),
        ('Saskatoon', 'z/Global%20SAS%20Player%20-%20Video%20Center'),
        ('Toronto', 'z/Global%20ON%20Player%20-%20Video%20Center'),
        ('Winnipeg', 'z/Global%20WIN%20Player%20-%20Video%20Center'),
    ]
    
    def get_cache_key(self):
        return "%s-%s" % (self.short_name, self.args.get('local_channel',''))
    
    def action_browse(self):
        self.PlayerTag = dict(self.local_channels)[self.args['local_channel']]
        
        if self.args['entry_id'] is None:
            return CanwestBaseChannel.action_root(self)
        return CanwestBaseChannel.action_browse(self)
        
    
    def action_root(self):
        for channel, ptag in self.local_channels:
            self.plugin.add_list_item({
                'Title': channel, 
                'action': 'browse',
                'channel': self.short_name, 
                'entry_id': None,
                'local_channel': channel
            })
        self.plugin.end_list()
    
    def get_categories_json(self, arg):
        return CanwestBaseChannel.get_categories_json(self, arg) + '&query=CustomText|PlayerTag|' + self.PlayerTag
    
    
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
                'use_rtmp': 1
            })
        self.plugin.end_list()

        
    def action_browse(self):
        soup = get_soup("http://%s/" % (self.args['remote_url'],))
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
                })
                self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()
        
class HistoryTV(CanwestBaseChannel):
    short_name = 'history'
    long_name = 'History TV'
    PID = 'IX_AH1EK64oFyEbbwbGHX2Y_2A_ca8pk'
    swf_url = 'http://www.history.ca/video/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/History%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url


class FoodNetwork(CanwestBaseChannel):
    short_name = 'foodnet'
    long_name = 'The Food Network'
    PID = '6yC6lGVHaVA8oWSm1F9PaIYc9tOTzDqY'
    #swf_url = 'http://webdata.globaltv.com/global/canwestPlayer/swf/4.1/flvPlayer.swf'

    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/FOODNET%20Player%20-%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url


class HGTV(CanwestBaseChannel):
    short_name = 'hgtv'
    long_name = 'HGTV.ca'
    PID = 'HmHUZlCuIXO_ymAAPiwCpTCNZ3iIF1EG'
    #swf_url = 'http://www.hgtv.ca/includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/HGTV%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url



class Showcase(CanwestBaseChannel):
    short_name = 'showcase'
    long_name = 'Showcase'
    PID = 'sx9rVurvXUY4nOXBoB2_AdD1BionOoPy'
    #swf_url = 'http://www.showcase.ca/video/swf/flvPlayer.swf'
    root_depth = 2
    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/Showcase%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    


class SliceTV(CanwestBaseChannel):
    short_name = 'slice'
    long_name = 'Slice TV'
    PID = 'EJZUqE_dB8XeUUgiJBDE37WER48uEQCY'
    #swf_url = 'http://www.slice.ca/includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/Slice%20Player%20-%20New%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url


class TVTropolis(CanwestBaseChannel):
    short_name = 'tvtropolis'
    long_name = 'TVtropolis'
    PID = '3i9zvO0c6HSlP7Fz848a0DvzBM0jUWcC'
    #swf_url = 'http://www.tvtropolis.com/swf/cwp/flvPlayer.swf'

    def get_categories_json(self, arg=None):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/TVTropolis%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url


class diyNet(CanwestBaseChannel):
    short_name = 'diynet'
    long_name = 'The DIY Network'
    PID = 'FgLJftQA35gBSx3kKPM46ZVvhP6JxTYt'
    #swf_url = 'http://www.diy.ca/Includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&query=CustomText|PlayerTag|z/DIY%20Network%20-%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url



class YTV(CanwestBaseChannel):
    short_name = 'ytv'
    long_name = 'YTV'
    PID = 't4r_81mEo8zCyfYh_AKeHJxmZleq26Vx'
    swf_url = 'http://www.ytv.com/PDK/swf/flvPlayer.swf'
    root_depth = 0
    
    def get_categories_json(self,arg):
        url = CanwestBaseChannel.get_categories_json(self,arg) + '&field=parentID&query=IncludeParents' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url


class TreehouseTV(CanwestBaseChannel):
    short_name = 'treehouse'
    long_name = 'Treehouse TV'
    PID = '6FTFywmxdSd_HKMYKQGFwsAf8rkcdn9R'
    swf_url = 'http://mediaparent.treehousetv.com/swf/flvPlayer.swf'
    root_depth = 0



class CBCChannel(ThePlatformBaseChannel):
    #is_abstract = True
    PID = "_DyE_l_gC9yXF9BvDQ4XNfcCVLS4PQij"
    base_url = 'http://cbc.feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    status = STATUS_UGLY
    short_name = 'cbc'
    long_name = 'CBC'
    category_cache_timeout = 0 # can't cache for CBC, need to drill-down each time

    #this holds an initial value for CBC only to get the top-level categories;
    #it is overwritten in action_root
    in_root = False
    category_json = '&query=ParentIDs|'
   
    def get_categories_json(self, arg):
        logging.debug('get_categories_json arg=%s, categ_json=%s'%(arg, self.category_json))
        url = ThePlatformBaseChannel.get_categories_json(self) + \
            '&customField=Account&customField=Show&customField=SeasonNumber&customField=AudioVideo&customField=ClipType&customField=LiveOnDemand'
        if arg or self.in_root:
            url += self.category_json
        if arg:
            url += arg
        return url

    #arg is CBC's customfield array from getReleases query
    def get_releases_json(self,arg):
        url = ThePlatformBaseChannel.get_releases_json(self)
        logging.warn("RELURL: %s" % (url,))
        if 'Account' in arg:
            url += '&query=ContentCustomText|Account|%s' % urlquoteval(arg['Account'])
        if 'Show' in arg:
            url += '&query=ContentCustomText|Show|%s' % urlquoteval(arg['Show'])
        if 'SeasonNumber' in arg:
            url += '&query=ContentCustomText|SeasonNumber|%s' % urlquoteval(arg['SeasonNumber'])
        if 'AudioVideo' in arg:
            url += '&query=ContentCustomText|AudioVideo|%s' % urlquoteval(arg['AudioVideo'])
        if 'ClipType' in arg:
            url += '&query=ContentCustomText|ClipType|%s' % urlquoteval(arg['ClipType'])
        if 'LiveOnDemand' in arg:
            url += '&query=ContentCustomText|LiveOnDemand|%s' % urlquoteval(arg['LiveOnDemand'])


        #url += '&query=CategoryIDs|%s'%arg['entry_id']
        logging.debug('get_releases_json: %s'%url)
        return url
        
    def get_child_categories(self, categorylist, parent_id):
        if parent_id is None:
            categories = [c for c in categorylist \
                          #if c['depth'] == 1 or c['depth'] == 0
                          if c['depth'] == 0
                          and (
                              self.plugin.get_setting('show_empty_cat') == True
                              or (c['hasReleases'] or c['hasChildren'])
                          )]
        else:
            #do nothing with parent_id in CBC's case
            categories = categorylist
        return categories

    def action_root(self):
        logging.debug('CBCChannel::action_root')
        
        #all CBC sections = ['Shows,Sports,News,Kids,Radio']
        self.category_json = ''
        self.in_root = True #just for annoying old CBC
        self.category_json = '&query=FullTitles|Shows,Sports,News,Kids,Radio'
        categories = self.get_categories(None)
        
        for cat in categories:
            cat.update({'Title': 'CBC %s'%cat['Title']})
            self.plugin.add_list_item(cat)
        self.plugin.end_list()

        #restore ParentIDs query for sub-categories
        self.category_json = '&query=ParentIDs|'
        self.in_root = False
        logging.debug('setting categ_json=%s'%self.category_json)


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
  
class TouTV(ThePlatformBaseChannel):
    long_name = 'Tou.TV'
    short_name='toutv'
    base_url = 'http://www.tou.tv/repertoire/'
    swf_url = 'http://static.tou.tv/lib/ThePlatform/4.2.9c/swf/flvPlayer.swf'
    default_action = 'root'
    
    categories = [
            ("animation","Animation"),
            ("entrevues-varietes", "Entrevues et varietes"),
            ("films-documentaires","Films et documentaires"),
            ("magazines-affaires-publiques", "Magazines et affaires publiques"),
            ("series-teleromans", "Series et teleromans"),
            ("spectacles-evenements", "Spectacles et evenements"),
            ("webteles",u"Webteles"),
    ]
  
    def action_browse_episode(self):
        url = self.args['remote_url']
        soup = get_soup(url)
        scripts = soup.findAll('script')
        
        epinfo_tag = [s for s in scripts if s.contents and s.contents[0].strip().startswith("// Get IP address and episode ID")][0]
        self.args['remote_PID'] = re.search(r"episodeId = '([^']+)'", epinfo_tag.contents[0].strip()).groups()[0]
        return ThePlatformBaseChannel.action_browse_episode(self)
        
    def action_play_episode(self):
        url = self.args['remote_url']
        soup = get_soup(url)
        scripts = soup.findAll('script')
        
        epinfo_tag = [s for s in scripts if s.contents and s.contents[0].strip().startswith("// Get IP address and episode ID")][0]
        self.args['remote_PID'] = re.search(r"episodeId = '([^']+)'", epinfo_tag.contents[0].strip()).groups()[0]
        return ThePlatformBaseChannel.action_play_episode(self)
        

    def action_play(self):
        parse = URLParser(swf_url=self.swf_url)
        self.plugin.set_stream_url(parse(self.args['clip_url']))        
            
    def action_browse_series(self):
        url = self.args['remote_url']
        soup = get_soup(url)
        for row in soup.findAll('div', {'class': 'blocepisodeemission'}):
            
            data = {}
            data.update(self.args)
            images = row.findAll('img')
            if len(images) == 2:
                image = images[1]
            else:
                image = images[0]
                
            title = decode_htmlentities(row.find('a', {'class': 'episode'}).b.contents[0],)[:-1]
            
            try:
                seasonp = [p for p in row.findAll('p') if 'class' in dict(p.attrs)][0]
                season = seasonp.contents[0].strip()
                title = season + ": " + title
            except:
                pass
                
            try:
                plotp = [p for p in row.findAll('p') if 'class' not in dict(p.attrs)][0]
                plot = plotp.contents[0].strip()
            except:
                plot = '(failed to fetch plot)'
                
                
            action = 'browse_episode'
            if self.plugin.get_setting("make_playlists") == "true":
                action = "play_episode"
                
            data.update({
                'action': action,
                'remote_url': 'http://tou.tv' + row.find('a')['href'],
                'Title': title,
                'Thumb': image['src'],
                'Plot': plot
            })
            self.plugin.add_list_item(data)
        self.plugin.end_list()
            
    def action_browse_category(self):
        cat = dict(self.categories)[self.args['category']]
        logging.debug("CAT: %s" % (cat,))
        url = self.base_url + self.args['category'] + "/"
        soup = get_soup(url)
        logging.debug(url)
        for a in soup.findAll('a', {'class': re.compile(r'bloc_contenu.*')}):
            data = {}
            data.update(self.args)
            data.update({
                'action': 'browse_series',
                'remote_url': 'http://tou.tv' + a['href'],
                'Title': a.find('h1').contents[0],
            })
            
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
    def action_root(self):
        
        for cat in self.categories:
            data = {}
            data.update(self.args)
            data.update({
                'channel': 'toutv',
                'action': 'browse_category',
                'category': cat[0],
                'Title': cat[1],
            })
            
            self.plugin.add_list_item(data)
        self.plugin.end_list()
        
        
