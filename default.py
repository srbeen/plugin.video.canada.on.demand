import os, sys
import shutil
import sha
import cgi
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import logging
logging.basicConfig(level=logging.DEBUG)
import urllib,urllib2
import time
from utils import urldecode
from channels import *
from channel import *
try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite
    
__plugin__ = "Canada On Demand"
__author__ = 'Andre,Renaud  {andrepleblanc,renaudtrudel}@gmail.com'
__url__ = 'http://xbmcaddons.com/addons/plugin.video.canada.on.demand/'
__date__ = '04-10-2011'
__version__ = '0.7.4'
__settings__ = xbmcaddon.Addon(id='plugin.video.canada.on.demand')



class OnDemandPlugin(object):
    
    def connect_to_db(self):
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.canada.on.demand/')
        if not os.path.exists(path):
            os.makedirs(path)
        self.db_conn = sqlite.connect(os.path.join(path, 'bookmarks.db'))
        curs = self.db_conn.cursor()
        curs.execute("""create table if not exists bookmark_folders (
            id integer primary key,
            name text,
            parent_id integer,
            path text
        )""")
        
        curs.execute("""create table if not exists bookmarks (
            id integer primary key,
            name text,
            folder_id integer,
            plugin_url text
        )""")

        try:
            curs.execute("""insert into bookmark_folders (id, name, parent_id, path) 
                        values (?,?,?,?)""", (1,'Bookmarks', 0, 'Bookmarks'))
        except:
            pass
        

    def _urlopen(self, url, retry_limit=4):
        retries = 0
        while retries < retry_limit:
            logging.debug("fetching %s" % (url,))
            try:            
                return urllib2.urlopen(url)
            except (urllib2.HTTPError, urllib2.URLError), e:
                retries += 1
            raise Exception("Failed to retrieve page: %s" %(url,))
    
    def _urlretrieve(self, url, filename, retry_limit=4):
        retries = 0
        while retries < retry_limit:
            logging.debug("fetching %s" % (url,))
            try:            
                return urllib.urlretrieve(url, filename)
            except (urllib.HTTPError, urllib.URLError), e:
                retries += 1
            raise Exception("Failed to retrieve page: %s" %(url,))
        
    def fetch(self, url, max_age=None):
        if max_age is None:
            return self._urlopen(url)

        tmpurl = url
        scheme, tmpurl = tmpurl.split("://",1)
        netloc, path = tmpurl.split("/",1)
        fname = sha.new(path).hexdigest()
        _dir = fname[:4]
        cacheroot = self.get_cache_dir()
        cachepath = os.path.join(cacheroot, netloc, _dir)
        if not os.path.exists(cachepath):
            os.makedirs(cachepath)

        download = True
        cfname = os.path.join(cachepath, fname)
        if os.path.exists(cfname):
            ctime = os.path.getctime(cfname)
            if time.time() - ctime < max_age:
                download = False
                
        if download:
            logging.debug("Fetching: %s" % (url,))
            urllib.urlretrieve(url, cfname)
        else:
            logging.debug("Using Cached: %s" % (url,))
            
        return open(cfname)
        
        
    
    def get_url(self,urldata):
        """
        Constructs a URL back into the plugin with the specified arguments.
        
        """
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))

    def action_channel_list(self):
        """
        List all registered Channels

        Channels are automatically registered simply by being imported 
        and being subclasses of BaseChannel.
        
        """
        minimum = int(self.get_setting("worst_channel_support"))
        for channel_code, channel_class in sorted(ChannelMetaClass.registry.channels.iteritems()):
            info = channel_class.get_channel_entry_info()

            # Default to <short_name>.png if no icon is set.
            if info['Thumb'] is None:
                info['Thumb'] = info['channel'] + ".png"

            try:
                info['Thumb'] = self.get_resource_path('images','channels', info['Thumb'])
            except ChannelException:
                logging.warn("Couldn't Find Channel Icon for %s" % (channel_code,))
            
            if channel_class.in_development and self.get_setting("show_dev_channels") == 'false': 
                continue
            
            if self.get_setting('awesome_librtmp') == "true":
                self.add_list_item(info)
            else:
                if channel_class.status >= minimum:
                    if channel_class.status == STATUS_BAD:                        
                        info['Title'] = info['Title'] + " [BAD]"
                    elif channel_class.status == STATUS_UGLY:
                        info['Title'] = info['Title'] + " [UGLY]"
                    self.add_list_item(info)
        self.end_list()
        
    def get_dialog(self):
        return xbmcgui.Dialog()
    
    def set_stream_url(self, url, info=None):
        """
        Resolve a Stream URL and return it to XBMC. 
        
        'info' is used to construct the 'now playing' information
        via add_list_item.
        
        """
        listitem = xbmcgui.ListItem(label='clip', path=url)
        xbmcplugin.setResolvedUrl(self.handle, True, listitem)
        
        
    
    def end_list(self, content='movies', sort_methods=None): 
        xbmcplugin.setContent(self.handle, content)
        if sort_methods is None:
            sort_methods = (xbmcplugin.SORT_METHOD_NONE,)
        
        for sm in sort_methods:
            xbmcplugin.addSortMethod(self.handle, sm)        
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)


    
    def get_cache_dir(self):
        """
        return an acceptable cache directory.
        
        """
        # I have no idea if this is right.
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.canada.on.demand/cache/')
        if not os.path.exists(path):
            os.makedirs(path)
        return path


    def get_setting(self, id):
        """
        return a user-modifiable plugin setting.
        
        """
        return __settings__.getSetting(id)


    def add_list_item(self, info, is_folder=True, return_only=False, 
                      context_menu_items=None, clear_context_menu=False, bookmark_parent=None, bookmark_id=None, bookmark_folder_id=None):
        """
        Creates an XBMC ListItem from the data contained in the info dict.
        
        if is_folder is True (The default) the item is a regular folder item
        
        if is_folder is False, the item will be considered playable by xbmc
        and is expected to return a call to set_stream_url to begin playback.

        if return_only is True, the item item isn't added to the xbmc screen but 
        is returned instead.
        
        
        Note: This function does some renaming of specific keys in the info dict.
        you'll have to read the source to see what is expected of a listitem, but in 
        general you want to pass in self.args + a new 'action' and a new 'remote_url'
        'Title' is also required, anything *should* be optional
        
        """
        if context_menu_items is None:
            context_menu_items = []
        
        if bookmark_parent is None:
            bookmark_url = self.get_url({'action': 'add_to_bookmarks', 'url': self.get_url(info)})
            context_menu_items.append(("Bookmark", "XBMC.RunPlugin(%s)" % (bookmark_url,)))
        else:
            bminfo = {'action': 'remove_from_bookmarks', 'url': self.get_url(info), 'folder_id': bookmark_parent}
            if bookmark_id is not None:
                bminfo['bookmark_id'] = bookmark_id
            elif bookmark_folder_id is not None:
                bminfo['bookmark_folder_id'] = bookmark_folder_id
                
            bookmark_url = self.get_url(bminfo)
            context_menu_items.append(("Remove From Bookmarks", "XBMC.RunPlugin(%s)" % (bookmark_url,)))
            
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
            context_menu_items.append(("Queue Item", "Action(Queue)"))
        
        li.setInfo(type='Video', infoLabels=dict((k, unicode(v)) for k, v in info.iteritems()))
        
        # Add Context Menu Items
        if context_menu_items:
            li.addContextMenuItems(context_menu_items, 
                                   replaceItems=clear_context_menu)
           
            
        # Handle the return-early case
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
        """
        Returns a full path to a plugin resource.
        
        eg. self.get_resource_path("images", "some_image.png")
        
        """
        p = os.path.join(__settings__.getAddonInfo('path'), 'resources', *path)
        if os.path.exists(p):
            return p
        raise ChannelException("Couldn't Find Resource: %s" % (p, ))

    def get_modal_keyboard_input(self, default=None, heading=None, hidden=False):
        keyb = xbmc.Keyboard(default, heading, hidden)
        keyb.doModal()
        val = keyb.getText()
        if keyb.isConfirmed():
            return val
        return None
    
    def get_existing_bookmarks(self):
        fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.get_cache_key(),))
        
            
    def add_bookmark_folder(self):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders order by path desc")
        rows = curs.fetchall()
        items = [r[3] for r in rows]
        dialog = self.get_dialog()
        val = dialog.select("Select a Parent for the New Folder", items)
        if val == -1:
            return None
        parent = rows[val]
        name = self.get_modal_keyboard_input('New Folder', 'Enter the name for the new folder')
        
        if name is None:
            return None

        newpath = parent[3]+"/"+name        
        curs = self.db_conn.cursor()
        curs.execute("select * from bookmark_folders where path=?", (newpath,))
        if curs.fetchall():
            dialog.ok("Failed!", "Couldn't create folder: %s because it already exists" % (newpath,))
            return None
        
        curs.execute("insert into bookmark_folders (name, parent_id, path) values (?, ?, ?)", (name, parent[0], newpath))
        curs.execute("select id, name, parent_id, path from bookmark_folders where path=?", (newpath,))
        self.db_conn.commit()
        return curs.fetchall()[0]
    
        
    def action_add_to_bookmarks(self):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders order by path asc")
        rows = curs.fetchall()
        logging.debug(rows)
        items = ["(New Folder)"]
        items += [r[3] for r in rows]
        dialog = self.get_dialog()
        val = dialog.select("Select a Bookmark Folder", items)
        logging.debug("VAL:%s" % (val,))    
        if val == -1:
            return xbmcplugin.endOfDirectory(self.handle, succeeded=False)
        
        elif val == 0:
            folder = self.add_bookmark_folder()
            if not folder:
                return xbmcplugin.endOfDirectory(self.handle, succeeded=False)
        else:
            logging.debug("ITEMS:%s" % (items,))
            logging.debug("ROWS:%s" % (rows,))
            folder = [r for r in rows if r[3]==items[val]][0]

        bm = urldecode(self.args['url'].split("?",1)[1])
        name = self.get_modal_keyboard_input(bm['Title'], 'Bookmark Title')
        if name is None:
            return None
        
        curs.execute("select * from bookmarks where folder_id = ? and plugin_url = ?", (folder[0], self.args['url']))
        if curs.fetchall():
            dialog.ok("Bookmark Already Exists", "This location is already bookmarked in %s" % (folder[3],))
            return None
        
        curs.execute("insert into bookmarks (name, folder_id, plugin_url) values (?,?,?)", (name, folder[0], self.args['url']))
        self.db_conn.commit()
        
        dialog.ok("Success!", "%s has been bookmarked!" % (name,))
        return xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def action_browse_bookmarks(self):
        folder_id = int(self.args['folder_id'])
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders where parent_id = ?", (folder_id,))
        for folder in curs.fetchall():
            self.add_list_item({
                'Thumb': self.get_resource_path("images", "bookmark.png"),
                'folder_id': folder[0],
                'Title': "[%s]" % (folder[1],),
                'action': 'browse_bookmarks',
            }, bookmark_parent=folder_id, bookmark_folder_id=folder[0])
        
        curs.execute("select id, name, plugin_url, folder_id from bookmarks where folder_id = ?", (folder_id,))
        logging.debug("Checking For Bookmarks")
        bookmarks = curs.fetchall()
        if not bookmarks:
            self.add_list_item({'Title': '-no bookmarks-'})
            
        else:
            for bm in bookmarks:
                data = urldecode(bm[2].split("?", 1)[1])
                data['Title'] = bm[1]
                self.add_list_item(data, is_folder=True, bookmark_parent=bm[3], bookmark_id=bm[0])
            
        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))
        
    def action_remove_from_bookmarks(self):
        logging.debug("REMOVE BOOKMARK: %s" % (self.args['url'],))
        is_folder = bool(self.args.get('bookmark_folder_id', False))
        parent_id = self.args['folder_id']
        if is_folder:
            return self.remove_folder_from_bookmarks(parent_id=parent_id, folder_id=self.args['bookmark_folder_id'])
        else:
            return self.remove_bookmark_from_bookmarks(parent_id=parent_id, bookmark_id=self.args['bookmark_id'])

        
    def remove_folder_from_bookmarks(self, parent_id, folder_id):
        curs = self.db_conn.cursor()        
        curs.execute("select id, name, parent_id, path from bookmark_folders where parent_id = ? and id = ?", (parent_id, folder_id))
        record = curs.fetchall()[0]
        dialog = self.get_dialog()
        if dialog.yesno("Are you Sure?", "Are you sure you wish to delete the bookmark folder: %s\n(All Bookmarks and Folders within it will be deleted!)" % (record[3],)):
            logging.debug("BM:Removing Bookmark Folder!")
            curs.execute("select id from bookmark_folders where path like ?", (record[3]+"%",))
            rows = curs.fetchall()
            for row in rows:
                logging.debug("deleting row: %s" % (row,))
                curs.execute("delete from bookmark_folders where id=?", row)
                curs.execute("delete from bookmarks where folder_id=?", row)
            self.db_conn.commit()
        return xbmc.executebuiltin("Container.Refresh")
        
        
    def remove_bookmark_from_bookmarks(self, parent_id, bookmark_id):
        curs = self.db_conn.cursor()        
        curs.execute("select id, name, folder_id, plugin_url from bookmarks where folder_id = ? and id = ?", (parent_id, bookmark_id))
        record = curs.fetchall()[0]
        dialog = self.get_dialog()
        if dialog.yesno("Are you Sure?", "Are you sure you wish to delete the bookmark: %s" % (record[1],)):
            logging.debug("BM:Removing Bookmark!")
            curs.execute("delete from bookmarks where folder_id = ? and id = ?", (parent_id, bookmark_id))
            self.db_conn.commit()
        else:
            logging.debug("They Said No?")
        return xbmc.executebuiltin("Container.Refresh")
    
    def action_plugin_root(self):
        self.add_list_item({
            'Title': 'Bookmarks',
            'action': 'browse_bookmarks',
            'folder_id': 1,
            'Thumb': self.get_resource_path("images", "bookmark.png")
        }, bookmark_parent=0)
        self.add_list_item({
            'Title': 'All Channels',
            'action': 'channel_list',
            'Thumb': os.path.join(__settings__.getAddonInfo('path'), 'icon.png')
        })
        self.end_list()
        
    def __call__(self):
        """
        This is the main entry point of the plugin.
        the querystring has already been parsed into self.args
        
        """
        
        action = self.args.get('action', None)
        
        if not action:
            action = 'plugin_root'
        
        
        if hasattr(self, 'action_%s' % (action,)):
            func = getattr(self, 'action_%s' % (action,))
            return func()
        
        # If there is an action, then there should also be a channel
        channel_code = self.args.get('channel', None)

        # The meta class has a registry of all concrete Channel subclasses
        # so we look up the appropriate one here.
        
        channel_class = ChannelMetaClass.registry.channels[channel_code]
        chan = channel_class(self, **self.args)
        
        return chan()
    
    def check_cache(self):
        cachedir = self.get_cache_dir()
        version_file = os.path.join(cachedir, 'version.0.7.0')
        if not os.path.exists(version_file):
            shutil.rmtree(cachedir)
            os.mkdir(cachedir)
            f = open(os.path.join(cachedir,"version.0.7.0"), 'w')
            f.write("\n")
            f.close()
        
    def __init__(self, script_url, handle, querystring):
        proxy = self.get_setting("http_proxy")
        port = self.get_setting("http_proxy_port")
        if proxy and port:
            proxy_handler = urllib2.ProxyHandler({'http':'%s:%s'%(proxy,port)})
            opener = urllib2.build_opener(proxy_handler)
            urllib2.install_opener(opener)

        self.script_url = script_url
        self.handle = int(handle)
        if len(querystring) > 2:
            self.querystring = querystring[1:]
            items = urldecode(self.querystring)
            self.args = dict(items)
        else:
            self.querystring = querystring
            self.args = {}
        self.connect_to_db()
        self.check_cache()
        logging.debug("Constructed Plugin %s" % (self.__dict__,))
        
if __name__ == '__main__':
    plugin = OnDemandPlugin(*sys.argv)
    plugin()
