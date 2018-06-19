import os
import json
import copy
import urllib
import argparse
from utils.cocoload import get_per_test_scored_file, get_per_test_file


def parse_view_args():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"PER_TEST_DIR", type=str,
		help="Directory containing per-test-coverage-reports. Must contain only " +
			 "JSON reports (or many folders of them)."
	)
	parser.add_argument(
		"-t", "--tests", nargs='+', required=True,
		help='Tests to look at.'
	)
	parser.add_argument(
		"-s", '--scores', nargs='+', type=float,
		help='[low, high] (inclusive): For looking at files with a score. ' +
			 'Ignored when --scoredfile is not used.'
	)
	parser.add_argument(
		"--getuniques", action="store_false", default=True,
		help='Returns unique lines for the test when a score range is given. (As a score of None indicates a unique test line). ' +
			 'Ignored when --scoredfile is not used.'
	)
	parser.add_argument(
		"--scoredfile", action="store_true", default=False,
		help='Set this flag if a file with the percent-change score is being looked at.'
	)
	return parser.parse_args()


def main():
	# Finds tests and shows the coverage for each of it's files.
	args = parse_view_args()

	DATA_DIR = args.PER_TEST_DIR
	test_files = args.tests
	score_range = args.scores
	scored_file = args.scoredfile
	ignore_uniques = args.getuniques

	tests_found = {tf: False for tf in test_files}

	for root, _, files in os.walk(DATA_DIR):
		for file in files:
			if scored_file:
				fmtd_test_dict = get_per_test_scored_file(
					DATA_DIR, file, return_test_name=True,
					score_range=score_range, ignore_uniques=ignore_uniques
				)
			else:
				fmtd_test_dict = get_per_test_file(
					DATA_DIR, file, return_test_name=True
				)
			print("From file: " + file)

			test_name = fmtd_test_dict['test']
			suite_name = fmtd_test_dict['suite']
			if test_name not in tests_found:
				continue
			tests_found[test_name] = True

			print("Test-name: " + test_name)
			print("Suite: " + suite_name)
			print("Unique coverage: \n" + "\n\n".join([str(sf) + ": " + str(fmtd_test_dict['source_files'][sf]) for sf in fmtd_test_dict['source_files'] if 'nsAppRunner' in sf]))
			print("\n")

	if not all([tests_found[test_name] for test_name in tests_found]):
		print(
			"Couldn't find the tests: \n" + 
			"\n".join([tests_found[test_name] for test_name in tests_found if not tests_found[test_name]])
		)

if __name__ == "__main__":
	main()