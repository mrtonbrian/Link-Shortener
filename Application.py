import sqlite3
import math
import os
from flask import Flask, render_template, request, redirect, Response, jsonify, send_from_directory, send_file
from requests import get
import csv
import glob
import time
import ast
from collections import defaultdict
import datetime
import itertools

app = Flask(__name__)

conn = sqlite3.connect('shortened_links.db')
c = conn.cursor()

c.execute(
    """CREATE TABLE IF NOT EXISTS shortened_links(currentCount integer, inpURL text, listOfConnectionTimes text, first_creation_timestamp integer)"""
)

date_generator = (datetime.datetime.today() - datetime.timedelta(days=i) for i in itertools.count())


@app.route('/reciever', methods=['POST'])
def setData():
    data = request.get_json(force=True)
    t = data['text']
    c.execute('SELECT EXISTS(SELECT 1 FROM shortened_links WHERE inpURL=? LIMIT 1);', (t,))
    res = c.fetchall()[0][0]
    if res == 0:
        c.execute('INSERT INTO shortened_links(currentCount, inpURL, first_creation_timestamp) VALUES (0, ?, ?)',
                  (t, time.time()))
        conn.commit()
    # https://stackoverflow.com/questions/15570096/sqlite-get-rowid
    c.execute('SELECT rowid FROM shortened_links WHERE inpURL=?', (t,))
    result = c.fetchall()
    ip = get_ip()
    # Temporary for My Current Port Forwarding Setup
    return ip + ':9999/' + base62_encode(int(result[0][0]))


def get_ip():
    return get('https://api.ipify.org').text


# Adapted from https://helloacm.com/base62/
def base62_encode(num, chars='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    r = num % 62
    res = chars[r]
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
    if not s:
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
        try:
            values = c.fetchall()[0]
            l = values[2]
            l = parse_list_from_string(l)
            l.append(int(time.time()))
            c.execute('UPDATE shortened_links SET currentCount=?, listOfConnectionTimes=? WHERE rowid=?',
                      (values[1] + 1, str(l), converted))
            conn.commit()
            return redirect(values[0])
        except IndexError:
            return render_template("404_Page.html")
        except Exception as e:
            print repr(e)
            return render_template('404_Page.html')


def create_csv_file(shortened_num, range_inp, org):
    c.execute('SELECT listOfConnectionTimes, first_creation_timestamp FROM shortened_links WHERE rowid=?',
              (base10(shortened_num),))
    fetched = c.fetchall()[0]
    l = parse_list_from_string(fetched[0])
    # Hopefully Should Reduce Collisions For Request's Temporary Filename
    fn = str((time.time()))

    if range_inp == 'all':
        # Converts Timestamp Difference To Days
        range_inp = abs((time.time() - fetched[1]) / 86400)

    # We Write To File To Always Ensure Proper Formatting
    fp = "CSV-Downloads/" + fn + ".csv"
    with open(fp, 'w') as csv_file:
        if org == 'today':
            currentDay = datetime.datetime.utcnow().strftime('%Y-%m-%d')
            fieldnames = ['Hour', 'Count']
            d = defaultdict(int)
            for i in l:
                timestamp_hour = timestampToHour(i)
                if timestamp_hour[1] == currentDay:
                    d[timestamp_hour[0]] += 1
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for i in xrange(0, 24):
                writer.writerow({"Hour": '{:02d}'.format(i) + ":00", "Count": d['{:02d}'.format(i) + ":00"]})
        else:
            connections_d = date_connection_dict_gen(l)
            dates_list = list(itertools.islice(date_generator, range_inp))

            # https://stackoverflow.com/a/993369/8935887
            new_dates_list = []
            for i in dates_list:
                new_dates_list.append(datetime_to_string(i))

            if org == "day":
                fieldnames = ['Date', 'Count']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                # new_dates_list Will Innately Be Sorted In Reverse, So All We Need To Do Is Reverse It
                new_dates_list = new_dates_list[::-1]
                for i in new_dates_list:
                    writer.writerow({"Date": i, "Count": connections_d[i]})

            elif org == "month":
                connections_m = month_connection_dict_gen(connections_d)
                fieldnames = ["Month", "Count"]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                months_list = []
                for i in connections_d:
                    months_list.append(i[0:7])
                months_list = list(set(months_list))
                months_list.sort()

                for i in months_list:
                    writer.writerow({"Month": i, "Count": connections_m[i]})
            else:
                connections_y = year_connection_dict_gen(connections_d)
                fieldnames = ["Year", "Count"]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                years_list = []
                for i in connections_d:
                    years_list.append(i[0:4])
                years_list = list(set(years_list))
                years_list.sort()

                for i in years_list:
                    writer.writerow({"Year": i, "Count": connections_y[i]})
    return fp


def datetime_to_string(date):
    return date.strftime("%Y-%m-%d")


def timestampToHour(ts):
    return [datetime.datetime.utcfromtimestamp(int(ts)).strftime("%H:00"),
            datetime.datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d')]


def date_connection_dict_gen(l):
    connections_d = defaultdict(int)
    for i in l:
        date = str(datetime.datetime.utcfromtimestamp(int(i)))[:10]
        connections_d[date] += 1
    return connections_d


def month_connection_dict_gen(date_conns):
    connections_dict = defaultdict(int)
    for i in date_conns.keys():
        connections_dict[i[0:7]] += date_conns[i]
    return connections_dict


def year_connection_dict_gen(date_conns):
    connections_dict = defaultdict(int)
    for i in date_conns.keys():
        connections_dict[i[0:4]] += date_conns[i]
    return connections_dict


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'Templates'), 'favicon.ico')


@app.route('/DefaultBackground.png')
def background():
    return send_from_directory(os.path.join(app.root_path, 'Templates'), 'DefaultBackground.png')


@app.route('/stats')
def stats():
    return render_template('Stats.html')


@app.route('/get-count', methods=['POST'])
def get_count():
    data = request.get_json(force=True)['URL']
    if '.' in data:
        data = data.split('/')[-1]
    c.execute('SELECT * FROM shortened_links where rowid=?', (data,))
    try:
        row = c.fetchall()[0]
    except IndexError:
        return "NOT FOUND"
    conn_dict = date_connection_dict_gen(parse_list_from_string(row[2]))

    filtered = {}

    dates_list = list(itertools.islice(date_generator, 3))

    for i in dates_list:
        filtered[datetime_to_string(i)] = conn_dict[i]

    return jsonify(count=row[0], url=row[1], count_per_day=filtered)


@app.route("/get-csv", methods=["POST"])
def get_csv():
    data = request.get_json(force=True)
    url = data['url'].split("/")[-1]

    # Clears All CSV Files
    files = glob.glob(os.path.join(os.path.join(os.getcwd(), "CSV-Downloads"), "*.csv"))
    for i in files:
        if i.endswith(".csv"):
            os.remove(i)
    if data['inp'] == 'today':
        fn = create_csv_file(url, 1, 'today')
    elif data['inp'] == 'week':
        fn = create_csv_file(url, 7, 'day')
    elif data['inp'] == 'month':
        fn = create_csv_file(url, 30, 'day')
    elif data['inp'] == 'year':
        fn = create_csv_file(url, 365, 'month')
    elif data['inp'] == 'all':
        fn = create_csv_file(url, 'all', data['sel'])
    return jsonify({'url': "/download/" + fn})


@app.route('/download/CSV-Downloads/<fn>')
def dl(fn):
    return send_from_directory("CSV-Downloads", fn, as_attachment=True)


if __name__ == '__main__':
    app.run('0.0.0.0', 5000)
    c.close()
