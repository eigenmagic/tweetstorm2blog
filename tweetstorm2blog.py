#!/usr/bin/env python3
# Grab a threaded tweetstorm and turn it into a blogpost
# Copyright Justin Warren <justin@eigenmagic.com>

import sys
import os.path
import argparse
import configparser
import time
import pprint
import collections

from urllib.parse import urlparse
import json

import tweepy

import pdb

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('tweets2blog')

class NoMoreTweets(Exception):
    """
    Raised if there are no more tweets to fetch.
    """

class TweetCache(object):
    """
    An abstracted class for storing a cache of tweet information.

    Backing store is just a file of raw JSON for now.
    """
    def __init__(self, filename):
        self.filename = filename
        pass

    def create_schema(self):
        return

    def get_tweets(self):
        # Try to load and parse any tweets we've already fetched
        fd = open(self.filename, "r")
        tweetset = json.load(fd)
        return(tweetset)

    def __len__(self):
        raise NotImplementedError("Need to count the length of the file.")

    def __delitem__(self, tweetid):
        raise NotImplementedError("How do we delete a single tweet?")

    def mark_deleted(self, tweetid):
        # Don't actually delete tweet, just mark it as deleted
        # This is so we can maintain a local archive, but know that
        # the public state of the tweet is deleted.
        #log.debug("Marking tweet id %id as deleted in cache...", tweetid)
        raise NotImplementedError("How do we mark a single tweet as deleted?")
        return

    def save_tweets(self, tweets):
        fd = open(self.filename, "w")
        json.dump([x._json for x in tweets], fd)
        fd.close()

def api_delay(args):
    """ Call to add a time delay based on the search ratelimit
    """
    sleeptime = 60 / args.searchlimit
    log.debug("sleeping for %s seconds...", sleeptime)
    time.sleep(sleeptime)

def load_tweetcache(args):
    """
    If we already have a cache of tweets, load it.

    Passes an empty dictionary if the cache doesn't exist.
    """
    tweetcache = TweetCache(os.path.expanduser(args.tweetcache))
    return tweetcache

def tweet_id_from_twurl(twurl):
    """ Parse the tweet ID from a tweet URL
    """
    scheme, netloc, path, params, query, fragment = urlparse(twurl)
    empty, handle, status, tweetid = path.split('/')
    return( int(tweetid) )

def fetch_all_tweets(tw, args, tweetcache):
    """
    Fetch tweet threads by starting with each tweet URL.

    We parse the tweet url to get the tweet id, then
    fetch that tweet and recursively fetch the tweets
    in the thread of replies until we reach the start of
    the tweetstorm.

    Then assemble the tweets into chronological order.
    """
    tweetlist = []
    for twurl in args.tweeturls:
        tweetid = tweet_id_from_twurl(twurl)

        tweetlist.extend(get_thread(tw, args, tweetcache, tweetid))

    tweetcache.save_tweets(tweetlist)
    return(tweetlist)

def fetch_user_replies(tw, args, tweetcache, tweetid, screen_name=None):
    """ Fetch replies to the tweet by the author.

    We're fetching a thread, so we ignore replies by other people
    and only search for the user replying to their own tweet.
    We'd use a get_thread API call to do this, but Twitter hates third-party devs,
    so there isn't one. ¯\_(ツ)_/¯
    """
    tweetlist = []
    #pp = pprint.PrettyPrinter(indent=2)

    # If we don't have a screen name, it's because this is the
    # first recursive call, so fetch the tweet_id and parse it
    if screen_name is None:
        tweet = tw.get_status(tweetid,
                          tweet_mode='extended',
                          include_entities=True,
                          trim_user=False,
                          )
        screen_name = tweet.user.screen_name

        tweetlist.append(tweet)
        #tweetdict[tweet['id']] = tweet

        log.debug("Found tweet!")

    # Find replies by the author to this tweet
    # We use result_type of 'recent' to get an ordered list, but this
    # orders from latest to earliest, so we need to do a kind of reverse-window
    # search working backwards until we have all the replies.
    finished = False
    since_id = tweetid
    max_id = None
    while not finished:
        # First iteration
        if max_id is None:
            results = tw.search_tweets(q="to:%s from:%s" % (screen_name, screen_name),
                            since_id=since_id,
                            count=100,
                            tweet_mode='extended',
                            result_type='recent',
                            include_entities=True,
                            trim_user=True)
        else:
            results = tw.search_tweets(q="to:%s from:%s" % (screen_name, screen_name),
                            since_id=since_id,
                            max_id=max_id,
                            count=100,
                            tweet_mode='extended',
                            result_type='recent',
                            include_entities=True,
                            trim_user=True)

        # log.debug("results: %s", pprint.pformat(results))
        
        log.debug("Found %d tweet replies", len(results))
        
        tweetlist.extend(results)

        # We found the maximum number of tweets, and there may be more, so we
        # need to find them.
        if len(results) == 100:
            log.info("Max replies found. Fetch again with narrowed search window.")
            # Set the parameters for the next fetching iteration
            max_id = min([x.id for x in results])
            log.debug("max_id to fetch is: %s", max_id)

        else:
            log.debug("Finished fetching replies.")
            # all done, break out of loop
            finished = True
            break

        # wait a bit before looping
        api_delay(args)

    return tweetlist

def get_thread(tw, args, tweetcache, start_tweetid):
    """
    Fetch a thread of tweets.

    The `start_tweetid` can be anywhere in the thread, as we search
    both upstream and downstream of this point to build the thread.

    Twitter only returns `in_reply_to` data for the tweet this
    tweet is in reply to. If you want to find the replies to this
    tweet, you have to use the search API and filter.

    We use `in_reply_to` to move backwards up the thread to find the start,
    and then we use the search functionality to find all the replies from the
    original author.
    """
    fetching = True
    log.debug("Fetching thread...")
    twthread = []
    tweetid = start_tweetid

    log.debug("Fetching tweets earlier in thread...")
    while(fetching):
        try:
            log.debug("Fetching tweet id: %s", tweetid)
            tweet = tw.get_status(tweetid,
                              tweet_mode='extended',
                              include_entities=True,
                              trim_user=True,
                            )
            #tweetset = tw.statuses.lookup(_id=tweetid, trim_user=False)
            #tweet = tw.statuses.oembed(_id=tweetid, trim_user=True)

            log.debug("tweet: %s", pprint.pformat(tweet))
            #log.debug("tweet: %s", json.dumps(json.loads('%s' % tweet), indent=4, sort_keys=True))

        except Exception as e:
            log.debug("Error! %s", e)
            fetching = False
            break

        twthread.append(tweet)

        if tweet.in_reply_to_status_id is None:
            fetching = False
            break

        tweetid = tweet.in_reply_to_status_id
        api_delay(args)

    # Try to find tweets later in the thread from this starting point
    log.debug("Fetching user replies...")
    tweets = fetch_user_replies(tw, args, tweetcache, start_tweetid)
    twthread.extend(tweets)

    log.debug("Fetched %d tweets.", len(twthread))

    return (twthread)

def blog_tweets(tweetlist):
    """ Create a blog from a list of tweets.
    """
    # We're just going to sort the tweets into chronological order
    # and then print the text out.
    tweetlist.sort(key=lambda tweet: tweet.id)
    tweetlist = { x.id: x for x in tweetlist } 

    # Sort the tweets by id so they're in (essentially) chronological order
    # As of Python 3.7, regular dicts are guaranteed to be ordered
    # tweetlist = collections.OrderedDict(tweetlist)

    # Do we have multiple authors?
    #authors = ', '.join([ x['user']['id_str'] for x in tweetlist.values()])
    #log.debug(authors)

    log.debug("Creating blog from %d unique tweets.", len(tweetlist))

    # We might want to bulk-fetch the oembed data for these tweets instead?

    # Only add replies if they are to one of the tweets in the main thread
    idlist = [sorted(tweetlist)[0]]
    blogtext = tweet_as_html(tweetlist[idlist[0]]) + '\n'
    for twtid in sorted(tweetlist)[1:]:
        tweet = tweetlist[twtid]
        if tweet.in_reply_to_status_id in idlist:
            idlist.append(twtid)
            blogtext += tweet_as_html(tweet) + '\n'
        else:
            log.debug(f"tweet not in reply to thread tweet, discarding: {tweet.full_text}")

    #pdb.set_trace()
    #blogtext = '\n'.join([ f"{x['created_at']}: {x['full_text']}" for x in tweetlist.values()])
    #blogtext = '\n'.join([ f"{x['full_text']}" for x in tweetlist.values()])
    # blogtext = '\n'.join([ tweet_as_html(x) for x in tweetlist.values()])

    # add a trailing newline
    # blogtext += '\n'
    return blogtext

def tweet_as_html(tw, quoted=False):
    """Convert a tweet into blog-ready html"""
    # log.debug("%s", pprint.pformat(tw))

    full_text = tw.full_text
    # Does this tweet have media entities?

    if hasattr(tw, 'entities'):

        if 'media' in tw.entities:
            # We have media, so figure out where they are in the text
            log.debug("Media found!")

            # FIXME: This won't work if there's more than one piece of media.
            for media in tw.entities['media']:
                log.debug("media indices are: %s", media['indices'])
                med_a = int(media['indices'][0])
                med_b = int(media['indices'][1])

                log.debug("text bits: %s", full_text[ med_a:med_b ])
                #tweet_text[]
                # We always slice out the shortcode URLs
                new_text = full_text[:med_a]

                # Replace the shortcode media URL with the actual URL as an html image
                if 'photo' in media['type']:
                    log.debug("Media is a photo.")
                    new_text += f"""<img src="{media['media_url_https']}"/>"""

                new_text += full_text[med_b:]
                full_text = new_text

        if 'urls' in tw.entities:
            #log.debug("URLs found")
            for url in tw.entities['urls']:
                idx_a = int(url['indices'][0])
                idx_b = int(url['indices'][1])
                new_text = full_text[:idx_a]
                new_text += f"""<a href="{url['expanded_url']}">{url['expanded_url']}</a>"""
                new_text += full_text[idx_b:]
                full_text = new_text

    log.debug("Full text rewritten to: %s", full_text)

    if hasattr(tw, 'quoted_status'):
        log.debug("Found quoted status.")
        quoted_text = tweet_as_html(tw.quoted_status, quoted=True)
        retstr = f'<p>{full_text}<p class="quoted">{quoted_text}</p></p>'
    else:
        retstr = f"<p>{full_text}</p>"

    return retstr
    
def augment_args(args):
    """
    Augment commandline arguments with config file parameters
    """
    cp = configparser.ConfigParser()
    cp.read(os.path.expanduser(args.config))

    return args

def authenticate(args):
    """
    Authenticate with Twitter and return an authenticated
    Twitter() object to use for API calls
    """
    # import the config file
    cp = configparser.ConfigParser()
    cp.read(os.path.expanduser(args.config))

    access_token = cp.get('twitter', 'access_token')
    access_token_secret = cp.get('twitter', 'access_token_secret')
    consumer_secret = cp.get('twitter', 'consumer_secret')
    consumer_key = cp.get('twitter', 'consumer_key')

    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret,
        access_token, access_token_secret
        )

    tw = tweepy.API(auth)

    return tw

if __name__ == '__main__':

    ap = argparse.ArgumentParser(description="Convert a Twitter thread into a blog.",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument('tweeturls', nargs='+', help="Tweet URLs")

    ap.add_argument('-c', '--config', default='~/.twitrc', help="Config file.")
    ap.add_argument('-o', '--outfile', default='./tweetblog.txt', help="Output file.")
    ap.add_argument('--tweetcache', default='./testcache.tmp', help="File to store cache of tweet/date IDs")

    #ap.add_argument('--fetchonly', action='store_true', help="Just run the fetch stage and then exit.")
    ap.add_argument('--nofetch', action='store_true', help="Skip the fetch stage.")
    ap.add_argument('--loglevel', choices=['debug', 'info', 'warning', 'error', 'critical'], help="Set log output level.")

    ap.add_argument('--searchlimit', type=int, default=5, help="Max number of searches per minute.")
    ap.add_argument('--deletelimit', type=int, default=60, help="Max number of deletes per minute.")

    args = ap.parse_args()

    if args.loglevel is not None:
        levelname = args.loglevel.upper()
        log.setLevel(getattr(logging, levelname))

    args = augment_args(args)

    # Log in to Twitter
    tw = authenticate(args)

    # Load cache of previous tweets, if we have one.
    tweetcache = load_tweetcache(args)

    # Load tweets from the cache if we don't fetch the live ones.
    if not args.nofetch:
        tweetlist = fetch_all_tweets(tw, args, tweetcache)
    else:
        tweetlist = tweetcache.get_tweets()

    # Write tweets out to our outfile as text
    with open(args.outfile, 'w') as fp:
        fp.write(blog_tweets(tweetlist))

    log.debug("Done.")
