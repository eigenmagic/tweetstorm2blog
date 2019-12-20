# TweetStorm2Blog

This is a basic Python 3 script to grab a thread of tweets from Twitter
and then spit them out as a text file so you can cut-and-paste them into
a blog.

## Configuration

You need to authorise the app with a Twitter access token for your Twitter account. Follow the instructions here: https://dev.twitter.com/oauth/overview/application-owner-access-tokens

Create a configuration file `~/.twitrc` in your home directory, and then add a
`[twitter]` section like so:

```
[twitter]
token = <your_api_token>
token_key = <your_token_key>
con_secret = <your_connection_secret>
con_secret_key = <your_connection_secret_key>
```

This file is designed to use the same format as https://github.com/eigenmagic/twitforget

## Usage

The standard way to use the script is to call it with the URL of one of the
tweets from the thread, like so:

`tweetstorm2blog.py https://twitter.com/<yourhandle>/status/<nnnnnnnnnnnnnn>`

For more advanced usage, run `tweetstorm2blog.py -h` to read the help.

## How It Works

The URL of the tweet you provide can be anywhere in the thread. The script will
work backwards from this starting point to find all the tweets earlier in the
thread, and then find all the replies to these tweets.

Once assembled, the script then sorts the tweets into chronological order and
prints them out as a text file.

You can specify the name of the output text file using `-o <outfile>`.
