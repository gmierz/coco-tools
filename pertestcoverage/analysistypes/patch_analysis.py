import os
import time
import logging
import numpy as np
from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata
)

HG_URL = "https://hg.mozilla.org/"

log = logging.getLogger('pertestcoverage')


def moving_average(data, n=3) :
    ret = np.cumsum(data, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:] / n


def running_mean(x, N):
    out = np.zeros_like(x, dtype=np.float64)
    dim_len = x.shape[0]
    for i in range(dim_len):
        if N%2 == 0:
            a, b = i - (N-1)//2, i + (N-1)//2 + 2
        else:
            a, b = i - (N-1)//2, i + (N-1)//2 + 1

        #cap indices to min and max indices
        a = max(0, a)
        b = min(dim_len, b)
        out[i] = np.mean(x[a:b])
    return out


def plot_histogram(data, x_labels, title, figure=None, **kwargs):
	if not figure:
		f = plt.figure()
	else:
		plt.figure(f.number)

	x = range(len(data))

	b = plt.bar(x, data, **kwargs)
	plt.xticks(x, x_labels, rotation='vertical')
	plt.title(title)

	return f, b


def run(args=None, config=None):
	"""
		Expects a `config` with the following settings:

			numpatches: 100
			startrev: "48cc597db296"
			outputdir: "C:/tmp/"
			analysisbranch: "mozilla-central"

			mochitest_tc_task_rev: "dcb3a3ba9065"
			mochitest_tc_task_branch: "try"
			xpcshell_tc_task_rev: "6369d1c6526b"
			xpcshell_tc_task_branch: "try" 

			analyze_files_with_missing_tests: True
	"""
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	numpatches = config['numpatches']
	startrevision = config['startrev']
	analysisbranch = config['analysisbranch']
	outputdir = config['outputdir']
	analyze_files_with_missing_tests = config['analyze_files_with_missing_tests']

	# JSON to use for test file queries
	mochitest_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":config['mochitest_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['mochitest_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":1000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	xpcshell_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":config['xpcshell_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['xpcshell_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":1000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	# Get all patches
	changesets = []
	keep_going = True
	currrev = startrevision

	while len(changesets) < numpatches:
		changelog_url = HG_URL + analysisbranch + "/json-log/" + currrev

		data = get_http_json(changelog_url)
		clog_csets_list = list(data['changesets'])
		changesets.extend([el['node'][:12] for el in clog_csets_list[:-1]])

		currrev = clog_csets_list[-1]['node'][:12]

	changesets = changesets[:numpatches]

	tests_for_changeset = {}
	tests_per_file = {}

	histogram1_datalist = []
	histogram2_datalist = []

	# For each patch
	for changeset in changesets:
		log.info("On changeset: " + changeset)

		# Get patch
		files_url = HG_URL + analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		if not files_modified:
			continue

		# Get tests that use this patch
		all_tests = set()

		if analyze_files_with_missing_tests:
			for file in files_modified:
				mochitest_query_json['where']['and'][0]['eq']['source.file.name'] = file
				xpcshell_query_json['where']['and'][0]['eq']['source.file.name'] = file

				try:
					mochi_tests = query_activedata(mochitest_query_json)
					xpc_tests = query_activedata(xpcshell_query_json)
				except Exception as e:
					log.info("Error running with file: " + file)

				if 'test' not in mochi_tests:
					mochi_tests['test'] = []
				if 'test' not in xpc_tests:
					xpc_tests['test'] = []

				tests_per_file[file] = list(set(mochi_tests['test']) | set(xpc_tests['test']))
				all_tests = list(set(all_tests) | (set(mochi_tests['test']) | set(xpc_tests['test'])))
		else:
			in_entry = {"in": {"source.file.name": files_modified}}
			groupby_entry = [{"name":"test","value":"test.name"}]

			if 'select' in mochitest_query_json:
				del mochitest_query_json['select']
			if 'select' in xpcshell_query_json:
				del xpcshell_query_json['select']

			mochitest_query_json['groupby'] = groupby_entry
			xpcshell_query_json['groupby'] = groupby_entry
			mochitest_query_json['where']['and'][0] = in_entry
			xpcshell_query_json['where']['and'][0] = in_entry

			try:
				mochi_tests = [testchunk[0] for testchunk in query_activedata(mochitest_query_json)]
				xpc_tests = [testchunk[0] for testchunk in query_activedata(xpcshell_query_json)]
			except Exception as e:
				log.info("Error running query: " + str(mochitest_query_json))
				log.info("or the query: " + str(xpcshell_query_json))

				mochi_tests = []
				xpc_tests = []

			all_tests = list(set(mochi_tests) | set(xpc_tests))

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Files with no tests: " + str([file for file in tests_per_file if file in files_modified and not tests_per_file[file]]))
		log.info("\n")

		tests_for_changeset[changeset] = {}
		tests_for_changeset[changeset]['patch-link'] = HG_URL + analysisbranch + "/rev/" + changeset
		tests_for_changeset[changeset]['numfiles'] = len(files_modified)
		tests_for_changeset[changeset]['numtests'] = len(all_tests)
		tests_for_changeset[changeset]['tests'] = all_tests

		histogram1_datalist.append((len(all_tests), changeset))
		histogram2_datalist.append((len(all_tests), len(files_modified), changeset))


	## Save results (number, and all tests scheduled)

	files_with_no_tests = {
		"files": [file for file in tests_per_file if not tests_per_file[file]]
	}

	log.info("\nSaving results to output directory: " + outputdir)
	save_json(tests_for_changeset, outputdir, str(int(time.time())) + '_tests_scheduled_per_changeset.json')

	if analyze_files_with_missing_tests:
		save_json(tests_per_file, outputdir, str(int(time.time())) + '_tests_scheduled_per_file.json')
		save_json(files_with_no_tests, outputdir, str(int(time.time())) + '_files_with_no_tests.json')


	## Plot the results

	f, b1 = plot_histogram(
		data=[numtests for numtests, _ in histogram1_datalist],
		x_labels=[changeset for _, changeset in histogram1_datalist],
		title="Tests scheduled (Y) over all changesets (X)"
	)

	ratioed_data = [numtests/numfiles if numfiles > 0 else 0 for numtests, numfiles, _ in histogram2_datalist]

	# Plot a second bar on top
	b2 = plt.bar(range(len(ratioed_data)), ratioed_data)
	plt.legend((b1[0], b2[0]), ('Number of tests', '# Tests per File'))

	plt.show()
