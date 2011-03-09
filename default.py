import os, sys
import cgi
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import logging
logging.basicConfig(level=logging.DEBUG)
logging.info("<------------Module Loaded----------------------->")
import urllib
from utils import urldecode
from channels import *


__plugin__ = "Canada On Demand"
__author__ = 'Andre <andrepleblanc@gmail.com>'
__url__ = 'http://andrepl.no-ip.org/'
__date__ = '03-09-2011'
__version__ = '0.0.1'
__settings__ = xbmcaddon.Addon(id='plugin.video.canada.on.demand')

class OnDemandPlugin(object):
    
    def get_url(self,urldata):
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))

    def channel_list(self):
        
        for channel_code, channel_class in ChannelMetaClass.registry.channels.iteritems():
            info = channel_class.get_channel_entry_info()
            logging.debug("CHANNEL INFO: %s" %(info,))
            if info['Thumb'] is None:
                info['Thumb'] = info['channel'] + ".png"
            info['Thumb'] = self.get_resource_path('images', info['Thumb'])
            
            self.add_list_item(info)
        self.end_list()
        
    def set_stream_url(self, url, info=None):
        listitem = xbmcgui.ListItem(label='clip', path=url)
        xbmcplugin.setResolvedUrl(self.handle, True, listitem)
        
        
    def end_list(self):
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

        
    def add_list_item(self, info, is_folder=True, return_only=False):

        info.setdefault('Thumb', 'None')
        info.setdefault('Icon', info['Thumb'])
        if 'Rating' in info:
            del info['Rating']
        
        li=xbmcgui.ListItem(
            label=info['Title'], 
            iconImage=info['Icon'], 
            thumbnailImage=info['Thumb']
        )
        
                
        if not is_folder:
            li.setProperty("IsPlayable", "true") 
        li.setInfo(type='Video', infoLabels=dict((k, unicode(v)) for k, v in info.iteritems()))

        if not return_only:
            kwargs = dict(
                handle=self.handle, 
                url=self.get_url(info),
                listitem=li,
                isFolder=is_folder
            )
            
            
            return xbmcplugin.addDirectoryItem(**kwargs)
        
        return li
        
    def get_resource_path(self, *path):
        p = os.path.join(__settings__.getAddonInfo('path'), 'resources', *path)
        if os.path.exists(p):
            return p
        raise ChannelException("Couldn't Find Resource: %s" % (p, ))
    
    def __call__(self):
        
        action = self.args.get('action', None)
        
        if not action:
            return self.channel_list()
        
        
        channel_code = self.args.get('channel', None)
        logging.debug("Action: %s, Channel: %s" % (action, channel_code))
        channel_class = ChannelMetaClass.registry.channels[channel_code]
        chan = channel_class(self, **self.args)
        return chan()
    
        
    def __init__(self, script_url, handle, querystring):
        
        logging.debug("Constructing Plugin with args: %s, %s, %s" % (script_url, handle, querystring))
        
        self.script_url = script_url
        self.handle = int(handle)
        if len(querystring) > 2:
            logging.debug("Parsing Querystring %s" % (querystring,))
            self.querystring = querystring[1:]
            items = urldecode(self.querystring)
            logging.debug("Parse QS Args: %s" % (items,))            
            self.args = dict(items)
            
        else:
            self.querystring = querystring
            self.args = {}
        
        logging.debug("Constructed Plugin %s" % (self.__dict__,))
        
if __name__ == '__main__':
    logging.info("Plugin Called With %s" % (sys.argv,))
    plugin = OnDemandPlugin(*sys.argv)
    plugin()
