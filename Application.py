import sqlite3
import math
import os
from flask import Flask, render_template, request, redirect, Response, jsonify, send_from_directory
from requests import get
import csv
import time
import ast
from collections import defaultdict
import datetime
import random
app = Flask(__name__)

conn = sqlite3.connect('shortened_links.db')
c = conn.cursor()

c.execute(
    """CREATE TABLE IF NOT EXISTS shortened_links(currentCount integer, inpURL text, listOfConnectionTimes text)""")


@app.route('/reciever', methods=['POST'])
def setData():
    data = request.get_json(force=True)
    t = data['text']
    c.execute('SELECT EXISTS(SELECT 1 FROM shortened_links WHERE inpURL=? LIMIT 1);', (t,))
    res = c.fetchall()[0][0]
    if res == 0:
        c.execute('INSERT INTO shortened_links(currentCount, inpURL) VALUES (0, ?)', (t,))
        conn.commit()
    # https://stackoverflow.com/questions/15570096/sqlite-get-rowid
    c.execute('SELECT rowid FROM shortened_links WHERE inpURL=?', (t,))
    result = c.fetchall()
    ip = get_ip()
    return ip + ':9999/' + base62_encode(int(result[0][0]))

def get_ip():
    return get('https://api.ipify.org').text

# Adapted from https://helloacm.com/base62/
def base62_encode(num, chars='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    r = num % 62
    res = chars[r];
    q = math.floor(num / 62)
    while q:
        r = q % 62
        q = math.floor(q / 62)
        res = chars[int(r)] + res
    return res


def base10(num, chars='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    result = 0
    for i in xrange(len(num)):
        result = 62 * result + chars.find(num[i])
    return result


def parse_list_from_string(s):
    if s == None:
        return []
    return ast.literal_eval(s)


@app.route('/', defaults={'url_code': '*'})
@app.route('/<url_code>')
def stuff(url_code):
    if url_code == '*':
        return render_template('Main_Page.html')
    else:
        converted = base10(url_code)
        c.execute('SELECT inpURL, currentCount, listOfConnectionTimes FROM shortened_links WHERE rowid=?', (converted,))
        values = c.fetchall()[0]
        try:
            l = values[2]
            l = parse_list_from_string(l)
            l.append(int(time.time()))
            c.execute('UPDATE shortened_links SET currentCount=?, listOfConnectionTimes=? WHERE rowid=?',
                      (values[1] + 1, str(l), converted))
            conn.commit()
            return redirect(values[0])
        except Exception as e:
            print repr(e)
            return render_template('404_Page.html')


def create_csv_file(shortened_num):
    c.execute('SELECT listOfConnectionTimes FROM shortened_links WHERE rowid=?', (base10(shortened_num),))
    l = parse_list_from_string(c.fetchall()[0][0])
    connections_d = date_connection_dict_gen(l)
    #Hopefully Should Reduce Collisions For Request's Filename
    fn = str(time.time())
    with open(fn,'w') as csv:
        fieldnames = ['Date','Count']
        writer = csv.DictWriter(csv,fieldnames=fieldnames)
        writer.writeheader()
        for i in connections_d.keys():
            writer.writerow({'Date': i,'Count':connections_d[i]})
    return fn

def date_connection_dict_gen(l):
    connections_d = defaultdict(int)
    for i in l:
        date = str(datetime.datetime.utcfromtimestamp(int(i)))[:10]
        connections_d[date] += 1
    return connections_d

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'Templates'), 'favicon.ico')


@app.route('/DefaultBackground.png')
def background():
    return send_from_directory(os.path.join(app.root_path, 'Templates'), 'DefaultBackground.png')


@app.route('/stats')
def stats():
    return render_template('Stats.html')

@app.route('/get-count',methods=['POST'])
def get_count():
    data = request.get_json(force=True)['URL']
    data = data.split('/')[1]
    c.execute('SELECT * FROM shortened_links where rowid=?',(data,))
    try:
        row = c.fetchall()[0]
    except IndexError:
        return "NOT FOUND"
    conn_dict = date_connection_dict_gen(parse_list_from_string(row[2]))
    return jsonify(count=row[0],url=row[1],count_per_day=conn_dict)
if __name__ == '__main__':
    app.run('0.0.0.0', 5000)
    c.close()
