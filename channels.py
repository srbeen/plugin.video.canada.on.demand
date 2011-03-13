import time
import simplejson
from channel import BaseChannel, ChannelException,ChannelMetaClass
from utils import *

class ThePlatformBaseChannel(BaseChannel):
    is_abstract = True
    #root_url = "getCategoryList?PID=%s&field=fullTitle&field=treeOrder&field=hasChildren&field=customData&field=description&field=parentID&field=title&field=ID&customField=AdCategory&customField=SortOrder&customField=Sub-Event&customField=Segment&customField=Producers&customField=Organizations&customField=LiveOnDemand&customField=EpisodeNumber&customField=ClipType&customField=Characters&customField=BylineCredit&customField=AudioVideo&customField=Aired&customField=CBCPersonalities&customField=People&customField=Event&customField=Region&customField=Sport&customField=SeasonNumber&customField=MaxClips&customField=SortField&customField=Show&customField=Genre&customField=CreatedBefore&customField=CreatedAfter&customField=Account&customField=GroupOrder&customField=GroupLevel&customField=IsDynamicPlaylist&customField=Keywords&customField=backgroundImage&query=FullTitles|News&callback=CBC.APP.UberPlayer.onGetCategoriesByTitle&callback=CBC.APP.UberPlayer.onGetCategoriesByParentID"

    #def get_root_url(self):
    #    return self.root_url % (self.PID,)
    #is_abstract = True
    #base_url = 'http://feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    #root_url = None
    base_url = None
    PID = None
    category_cache_timeout = 1 # value is in seconds. so 5 minutes.

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


    def get_cached_categories(self, parent_id):
        
        categories = None

        fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.short_name,))
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
                        if dict['value'] == '(not specified)':
                            dict['value'] = '\'\''
                        if dict['value'] != '':
                            data.update({dict['title']: dict['value']},) #urlquoteval(dict['value'])
            logging.debug(data)
                
            #logging.debug('hasChildren%s or hasReleases%s'%(c['hasChildren'],c['hasReleases']))
            #if c['hasReleases'] or c['hasChildren']:
            #    data.update({'remote_url': '',})
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
            logging.debug(item)
            if item['bitrate'] != '':
                title = '%s (%d kbps)'%(item['title'],int(item['bitrate'])/1024)
            else:
                title = item['title']
            rels.append({
                'Thumb': item['thumbnailURL'],
                'Title': title,
                'Plot': item['description'],
                'entry_id': item['ID'],
                'remote_url': item['URL'],
                'remote_PID': item['PID'],
                'channel': self.args['channel'],
                'action': 'browse_episode',
            })
        return rels


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


    def action_root(self):
        logging.debug('ThePlatformBaseChannel::action_root')
        parent_id = self.args['entry_id'] # this should be None from @classmethod
        categories = self.get_categories(parent_id)# and root=true
        for cat in categories:
            self.plugin.add_list_item(cat)
        self.plugin.end_list()


    def action_play(self):
        self.plugin.set_stream_url(transform_stream_url(self.args['clip_url'], self.swf_url))


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



class CTVBaseChannel(BaseChannel):
    is_abstract = True
    root_url = 'VideoLibraryWithFrame.aspx'

    def action_play_clip(self):
        rurl = "http://esi.ctv.ca/datafeed/urlgenjs.aspx?vid=%s" % (self.args['ClipId'],)
        data = transform_stream_url(get_page(rurl).read().strip()[17:].split("'",1)[0], self.swf_url)
        url = data
        if self.args.get('use_rtmp') and url.startswith("rtmpe://"):
            url = "rtmp://" + url[8:]
        self.plugin.set_stream_url(url)


    def action_browse(self):
        rurl = self.get_url(self.args['remote_url'])
        div = get_soup(rurl).find('div', {'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = levelclass[5:]
        if levelclass == '4': # Browsing at the clip level
                              # We want to build a context menu
                              # Item to allow 're-browsing' this directory
                              # with forced rtmpe urls.
            menu_args = {}
            menu_args.update(self.args)

            if self.args.get('use_rtmp'):
                del menu_args['use_rtmp']
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



class CanwestBaseChannel(ThePlatformBaseChannel):
    is_abstract = True
    base_url = 'http://feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    PID = None

    def get_categories_json(self):#,arg):
        return ThePlatformBaseChannel.get_categories_json(self) # + '&query=ParentIDs|%s'%arg

    def get_releases_json(self,arg='0'):
        return ThePlatformBaseChannel.get_releases_json(self) + '&query=CategoryIDs|%s'%arg['entry_id']

    def get_child_categories(self, categorylist, parent_id):
        if parent_id is None:
            categories = [c for c in categorylist \
                          if c['depth'] == 1
                          and (
                              self.plugin.get_setting('show_empty_cat') == True
                              or (c['hasReleases'] or c['hasChildren'])
                          )]
        else:
            cat = [c for c in categorylist if c['ID'] == int(parent_id)][0]
            categories = [c for c in categorylist \
                        if c['fullTitle'].startswith(cat['fullTitle'] + "/") 
                        and c['depth'] == cat['depth'] + 1 
                        ]
            """
                      and (
                          self.plugin.get_setting('show_empty_cat') == True
                          or (c['hasReleases'] or c['hasChildren'])
                      )]
            """
        return categories

    #is folding-back into ThePlatformBase even possible??
    def action_browse_episode(self):
        #url = "http://release.theplatform.com/content.select?format=SMIL&mbr=true&pid=%s" % (self.args['remote_PID'],)
        url= 'http://release.theplatform.com/content.select?pid=%s&UserName=Unknown&Embedded=True&Portal=History&Tracking=True'%(self.args['remote_PID'],)
        logging.debug('action_browse_episode: url=%s'%url)
        soup = get_stone_soup(url)
        logging.debug("StoneSOUP: %s" % (soup,))

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
            data['clip_url'] = clip_url
            data['action'] = 'play'
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()


    #override ThePlatFormbase so ?querystring isn't included in playpath 
    #this could be temp-only, actually. paypath doesn't seem to care about extra parameters
    def action_play(self):
        #rtmp://cp68811.edgefcs.net/ondemand/?auth=dbEa5aUbNbNaYasbMcgdub9aVaOatcfbraO-bnExkl-4q-d9i-8nrEJoTnwC5N9&amp;aifp=1234&amp;slist=Canwest_Broadcast_Entertainment/ playpath=Canwest_Broadcast_Entertainment/History_Ancients_S1_Ep1004_V2 swfurl=http://www.history.ca/video/cwp/swf/flvPlayer.swf swfvfy=true
        #rtmp://cp68811.edgefcs.net/ondemand?ovpfv=2.1.4&auth=dbEcOb.dad3dgdddiaOdubsdlcPcEbTbxcZ-bnExxk-4q-d9i-1onGAqPqCF0P9&aifp=1234&slist=Canwest_Broadcast_Entertainment/ playpath=Canwest_Broadcast_Entertainment/History_Ancients_S1_Ep1006?auth=dbEcOb.dad3dgdddiaOdubsdlcPcEbTbxcZ-bnExxk-4q-d9i-1onGAqPqCF0P9&aifp=1234&slist=Canwest_Broadcast_Entertainment/ swfurl=http://www.history.ca/video/cwp/swf/flvPlayer.swf swfvfy=true
        self.plugin.set_stream_url(transform_stream_url(self.args['clip_url'], self.swf_url, playpath_qs=False))



class GlobalTV(CanwestBaseChannel):
    short_name = 'global'
    long_name = 'Global TV'
    PID = 'W_qa_mi18Zxv8T8yFwmc8FIOolo_tp_g'
    #swf_url = 'http://www.globaltv.com/video/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/Global%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class HistoryTV(CanwestBaseChannel):
    short_name = 'history'
    long_name = 'History TV'
    PID = 'IX_AH1EK64oFyEbbwbGHX2Y_2A_ca8pk'
    swf_url = 'http://www.history.ca/video/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/History%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class FoodNetwork(CanwestBaseChannel):
    short_name = 'foodnet'
    long_name = 'The Food Network'
    PID = '6yC6lGVHaVA8oWSm1F9PaIYc9tOTzDqY'
    #swf_url = 'http://webdata.globaltv.com/global/canwestPlayer/swf/4.1/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/FOODNET%20Player%20-%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class HGTV(CanwestBaseChannel):
    short_name = 'hgtv'
    long_name = 'HGTV.ca'
    PID = 'HmHUZlCuIXO_ymAAPiwCpTCNZ3iIF1EG'
    #swf_url = 'http://www.hgtv.ca/includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/HGTV%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class Showcase(CanwestBaseChannel):
    short_name = 'showcase'
    long_name = 'Showcase'
    PID = 'sx9rVurvXUY4nOXBoB2_AdD1BionOoPy'
    #swf_url = 'http://www.showcase.ca/video/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/Showcase%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class SliceTV(CanwestBaseChannel):
    short_name = 'slice'
    long_name = 'Slice TV'
    PID = 'EJZUqE_dB8XeUUgiJBDE37WER48uEQCY'
    #swf_url = 'http://www.slice.ca/includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/Slice%20Player%20-%20New%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class TVTropolis(CanwestBaseChannel):
    short_name = 'tvtropolis'
    long_name = 'TVtropolis'
    PID = '3i9zvO0c6HSlP7Fz848a0DvzBM0jUWcC'
    #swf_url = 'http://www.tvtropolis.com/swf/cwp/flvPlayer.swf'

    def get_categories_json(self):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/TVTropolis%20Player%20-%20Video%20Center' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url


class diyNet(CanwestBaseChannel):
    short_name = 'diynet'
    long_name = 'The DIY Network'
    PID = 'FgLJftQA35gBSx3kKPM46ZVvhP6JxTYt'
    #swf_url = 'http://www.diy.ca/Includes/cwp/swf/flvPlayer.swf'

    def get_categories_json(self,arg):#='0'):
        url = CanwestBaseChannel.get_categories_json(self) + '&query=CustomText|PlayerTag|z/DIY%20Network%20-%20Video%20Centre' #urlencode
        logging.debug('get_categories_json: %s'%url)
        return url

    def get_releases_json(self,arg='0'):
        url = '%s' % CanwestBaseChannel.get_releases_json(self,arg)
        logging.debug('get_releases_json: %s'%url)
        return url





class CBCChannel(ThePlatformBaseChannel):
    #is_abstract = True
    PID = "_DyE_l_gC9yXF9BvDQ4XNfcCVLS4PQij"
    base_url = 'http://cbc.feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    
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
        if 'Account' in arg:
            url += '&query=ContentCustomText|Account|%s'%urlquoteval(arg['Account'])
        if 'Show' in arg:
            url += '&query=ContentCustomText|Show|%s'%urlquoteval(arg['Show'])
        if 'SeasonNumber' in arg:
            url += '&query=ContentCustomText|SeasonNumber|%s'%urlquoteval(arg['SeasonNumber'])
        if 'AudioVideo' in arg:
            url += '&query=ContentCustomText|AudioVideo|%s'%urlquoteval(arg['AudioVideo'])
        if 'ClipType' in arg:
            url += '&query=ContentCustomText|ClipType|%s'%urlquoteval(arg['ClipType'])
        if 'LiveOnDemand' in arg:
            url += '&query=ContentCustomText|LiveOnDemand|%s'%urlquoteval(arg['LiveOnDemand'])


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
        """
        categories = [c for c in categorylist] \
                      if (
                          self.plugin.get_setting('show_empty_cat') == True
                          or (c['hasReleases'] or c['hasChildren'])
                      )]
        """
        return categories


    #is folding-back into ThePlatformBase even possible??
    def action_browse_episode(self):
        """
        Handles browsing the clips within an episode.

        """
        
        url = 'http://release.theplatform.com/content.select?&pid=%s&format=SMIL&mbr=true' % (self.args['remote_PID'],)
        soup = get_soup(url)
        logging.debug("SOUP: %s" % (soup,))
        base_url = decode_htmlentities(soup.meta['base'])
        
        try:
            base_url, qs = base_url.split("?",1)
        except ValueError:
            base_url = base_url
            qs = None
            
        logging.debug({'qs': qs, 'base_url': base_url})

        for i, vidtag in enumerate(soup.findAll('video')):
            ref = vidtag.ref
            if ref is None:
                ref = vidtag
            clip_url = base_url + ref['src']

            if qs:
                clip_url += "?" + qs

            data = {}
            data.update(self.args)
            data['Title'] = self.args['Title'] + " clip %s" % (i+1,)
            data['clip_url'] = clip_url
            data['action'] = 'play'
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list()


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


"""

class CBCTelevision(CBCBaseChannel):
    short_name = 'cbctv'
    long_name = 'CBC Television'
    #cbcsection = '1221254309'
    cbcsection = 'Shows'
    
    def get_categories_json(self):
        url = '%sShows' % CBCBaseChannel.get_categories_json(self)
        logging.debug('get_categories_json: %s'%url)
        return url

class CBCNews(CBCBaseChannel):
    short_name = 'cbcnews'
    long_name = 'CBC News'
    cbcsection = 'News'    

    def get_categories_json(self):
        url = '%sNews' % CBCBaseChannel.get_categories_json(self)
        logging.debug('get_categories_json: %s'%url)
        return url


class CBCSports(CBCBaseChannel):
    short_name = 'cbcsports'
    long_name = 'CBC Sports'
    cbcsection = 'Sports'    

    def get_categories_json(self):
        url = '%sSports' % CBCBaseChannel.get_categories_json(self)
        logging.debug('get_categories_json: %s'%url)
        return url



class CBCKids(CBCBaseChannel):
    short_name = 'cbckids'
    long_name = 'CBC Kids'
    cbcsection = 'Kids'    

    def get_categories_json(self):
        url = '%sKids' % CBCBaseChannel.get_categories_json(self)
        logging.debug('get_categories_json: %s'%url)
        return url


class CBCRadio(CBCBaseChannel):
    short_name = 'cbcradio'
    long_name = 'CBC Radio'
    cbcsection = 'Radio'    

    def get_categories_json(self):
        url = '%sRadio' % CBCBaseChannel.get_categories_json(self)
        logging.debug('get_categories_json: %s'%url)
        return url
"""





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
