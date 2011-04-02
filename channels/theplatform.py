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
        make_playlists = self.plugin.get_setting('make_playlists') == 'true'
        max_bitrate = int(self.plugin.get_setting('max_bitrate'))
        
        rels = []
        for item in data['items']:
            item['bitrate'] = int(item['bitrate'])/1024
            if (not rels) or (rels[-1]['Title'] != item['title']):
                
                action = 'browse_episode'
                if make_playlists:
                    action = 'play_episode'
                
                rels.append({
                    'Thumb': item['thumbnailURL'],
                    'Title': item['title'],
                    'Plot': item['description'],
                    'entry_id': item['ID'],
                    'remote_url': item['URL'],
                    'remote_PID': item['PID'],
                    'channel': self.args['channel'],
                    'action': action,
                    'bitrate': item['bitrate'],
                })

            else:
                if item['bitrate'] <= max_bitrate and item['bitrate'] > rels[-1]['bitrate']:
                    rels.pop()
                    action = 'browse_episode'
                    if make_playlists:
                        action = 'play_episode'
                    
                    rels.append({
                        'Thumb': item['thumbnailURL'],
                        'Title': item['title'],
                        'Plot': item['description'],
                        'entry_id': item['ID'],
                        'remote_url': item['URL'],
                        'remote_PID': item['PID'],
                        'channel': self.args['channel'],
                        'action': action,
                        'bitrate': item['bitrate'],
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
        }


    
    
