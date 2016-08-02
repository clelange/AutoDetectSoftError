#!/usr/bin/env python

"""Automatically run DetectSoftError for CMS pixel detector once a certain
   amount of integrated luminosity has been delivered by the LHC
"""

import requests
import xmltodict
import logging
import logging.handlers
from datetime import datetime
from threading import Timer, Event
from time import sleep

# Settings for running:
# set time out for the query:
timeOut = 30
# threshold in 1/pb
lumiThreshold = 100.0
# last int. lumi value DetectSoftError has been called
lastDetSoftErrLumi = 0

currentVersion = 1.1
wbmBaseUrl = 'http://cmswbm.cms/cmsdb/servlet/'
wbmFormat = '?XML=1'
wbmTimeFormat = '%Y.%m.%d %H:%M:%S'
pixelSupervisorBaseUrl = "http://srv-s2b18-10-01.cms:1970/urn:xdaq-application:lid=51/"
pixelSupervisorHandler = "StateMachineXgiHandler"
pixelSupervisorPayload = {"StateInput": "DetectSoftError"}
pixelSupervisorDefaultPage = "Default"

# set up the logging
logFileName = 'AutoDetectSoftError.log'
myLogger = logging.getLogger("AutoDetectSoftError")
myLogger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fileHandler = logging.handlers.RotatingFileHandler(
    logFileName, delay=True, backupCount=5)
fileHandler.setLevel(logging.DEBUG)
# create console handler with a higher log level
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fileHandler.setFormatter(formatter)
consoleHandler.setFormatter(formatter)
# add the handlers to the logger
myLogger.addHandler(fileHandler)
myLogger.addHandler(consoleHandler)


class RepeatedTimer(object):

    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


def queryPageZero():

    # query PageZero and convert into dictionary
    pageZeroDict = {}
    pageZero = requests.get('{0}PageZero{1}'.format(wbmBaseUrl, wbmFormat))
    if (pageZero.status_code != requests.codes.ok):
        myLogger.error('PageZero returned status code {0}'.format(
            pageZero.status_code))
        return pageZeroDict
    try:
        pageZeroDict = xmltodict.parse(pageZero.content)
    except:
        myLogger.error(
            'PageZero returned non valid data\n{0}'.format(pageZero.content))
        return pageZeroDict
    try:
        pageZeroDict = pageZeroDict["monitor"]["PageZeroSample"]
    except KeyError:
        myLogger.error(
            'PageZero does not contain required data\n{0}'.format(pageZeroDict))
        return {}
    return pageZeroDict


def queryPixelSupervisor():

    isRunning = False
    pixelSuper = requests.get('{0}{1}'.format(
        pixelSupervisorBaseUrl, pixelSupervisorDefaultPage))
    if (pixelSuper.status_code != requests.codes.ok):
        myLogger.error('PageZero returned status code {0}'.format(
            pageZero.status_code))
    else:
        statusLine = ""
        fullPage = pixelSuper.content
        # find the line containing the pixel status
        for line in fullPage.splitlines():
            if line.find("Current State") >= 0:
                statusLine = line
                break
        # extract the actual state
        statusStart = statusLine.find("<b>") + 3
        statusEnd = statusLine.find("</b>")
        status = statusLine[statusStart:statusEnd]
        myLogger.debug("PixelSupervisor status: {0}".format(status))
        if (status == "Running"):
            isRunning = True
    return isRunning


def queryRunParameters(runNumber, timeNow, instantLumi):

    # return time since last FixingSoftError
    intLumiSinceLastDetSoftErr = -1
    runParams = requests.get('{0}RunParameters?RUN={1}'.format(
        wbmBaseUrl, runNumber))
    if (runParams.status_code != requests.codes.ok):
        myLogger.error('RunParameters returned status code {0}'.format(
            pageZero.status_code))
    else:
        statusLine = ""
        fullPage = runParams.content
        # find the line containing the pixel status
        for line in reversed(fullPage.split('</TR>')):
            if line.find("PIXEL_STATE") >= 0:
                if line.find("RunningSoftErrorDetected") >= 0:
                    statusLine = line
                    print statusLine
                    break
        if (statusLine != ""):
            # extract the actual state
            statusStart = statusLine.rfind("<TD>") + 4
            statusEnd = statusLine.rfind("</TD>")
            lastDetSoftErrTimeWBM = statusLine[statusStart:statusEnd]
            myLogger.info("Last time RunningSoftErrorDetected as from WBM: {0}".format(lastDetSoftErrTimeWBM))
            lastDetSoftErrTime = datetime.strptime(lastDetSoftErrTimeWBM, wbmTimeFormat)
            myLogger.debug("Last time RunningSoftErrorDetected: {0}".format(lastDetSoftErrTime.isoformat(' ')))
            tDelta = timeNow - lastDetSoftErrTime
            tDeltaSeconds = ((tDelta.microseconds + (tDelta.seconds +
                                                     tDelta.days * 24 * 3600) * 10**6) / 10**6)
            myLogger.info("Difference in seconds: {0}".format(tDeltaSeconds))
            # calculate integrated lumi in pb-1 (from 1e30 cm-2 s-1), :
            intLumiSinceLastDetSoftErr = tDeltaSeconds * instantLumi / 1e6
            myLogger.info("Pessimistic integrated luminosity since RunningSoftErrorDetected: {0}".format(intLumiSinceLastDetSoftErr))

    return intLumiSinceLastDetSoftErr


def statusLoop():

    global lastDetSoftErrLumi
    timeNow = datetime.utcnow()
    myLogger.debug("Time of execution: {0}".format(timeNow))

    pageZeroDict = queryPageZero()

    # check that we are looking at up-to-date information
    collectionTimeGMT = pageZeroDict["collectionTimeGMT"]
    updateTime = datetime.strptime(collectionTimeGMT, wbmTimeFormat)
    myLogger.debug("CMS update time: {0}".format(updateTime.isoformat(' ')))
    tDelta = timeNow - updateTime
    tDeltaSeconds = ((tDelta.microseconds + (tDelta.seconds +
                                             tDelta.days * 24 * 3600) * 10**6) / 10**6)
    myLogger.debug("Difference in seconds: {0}".format(tDeltaSeconds))
    if (tDeltaSeconds < -1) or (tDeltaSeconds > 20):
        myLogger.warning(
            "PageZero time ahead of current time (bug in code?) or is lagging behind more than 20 seconds, time difference in seconds: {0}".format(tDeltaSeconds))
        return

    # a few sanity checks:
    # check that we are in stable beams
    stableBeams = (pageZeroDict["BMODEtag"] == "STABLE")
    myLogger.debug("Stable Beams: {0}".format(stableBeams))
    if not stableBeams:
        return

    # check that pixels are included in the run
    pixelIn = (pageZeroDict["IO_PIXEL"] == "IN")
    myLogger.info("Pixel in the run: {0}".format(pixelIn))
    if not pixelIn:
        return

    # check that PixelSupervisor is running
    pixelRunning = queryPixelSupervisor()
    myLogger.info("Pixel running: {0}".format(pixelRunning))
    if not pixelRunning:
        myLogger.info("PixelSupervisor running: {0}".format(pixelRunning))
        return

    # get integrated lumi and run number for current run:
    lumiRun = 0
    runNumber = 0
    try:
        if not (pageZeroDict["lumiRun"] == "Infinity"):
            lumiRun = float(pageZeroDict["lumiRun"])
        runNumber = int(pageZeroDict["runNumber"])
    except:
        myLogger.error('Luminosity or run number for current run not available: {0} - {1}'.format(
            lumiRun, runNumber))
        return
    myLogger.info(
        "Luminosity for current run {0} is: {1} pb-1".format(runNumber, lumiRun))

    # calculate whether threshold for DetectSoftError is reached
    if not ((lumiRun - lastDetSoftErrLumi) > lumiThreshold):
        myLogger.info("Threshold for DetectSoftError not yet reached, only {0} pb-1 (relative, total {1} pb-1) have passed, {2} pb-1 needed".format(
            lumiRun - lastDetSoftErrLumi, lumiRun, lumiThreshold))
        return

    # get instantaneous lumi for some calculations:
    instantLumi = 0
    if not (pageZeroDict["instantLumi"] == "Infinity"):
        instantLumi = float(pageZeroDict["instantLumi"])
    myLogger.debug("Instantaneuous luminosity [1e30 cm-2 s-1]: {0}".format(instantLumi))
    if (instantLumi == 0):
        return

    myLogger.info("General threshold for DetectSoftError reached, {0} pb-1 have passed".format(
        lumiRun - lastDetSoftErrLumi))

    # get integrated lumi since last DetectSoftError
    intLumiSinceLastDetSoftErr = queryRunParameters(runNumber, timeNow, instantLumi)
    # trigger DetectSoftError if mechanism has not yet been called for run or threshold has been reached
    if (intLumiSinceLastDetSoftErr < 0):
        myLogger.info("DetectSoftError does not seem to have been triggered for this run ({})".format(intLumiSinceLastDetSoftErr))
    elif (intLumiSinceLastDetSoftErr > lumiThreshold):
        myLogger.info("Threshold for DetectSoftError reached, {0} pb-1 have passed".format(intLumiSinceLastDetSoftErr))
    else:
        myLogger.info("Threshold has not been reached yet since last DetectSoftError,  {0} pb-1 have passed".format(intLumiSinceLastDetSoftErr))
        return


    # now call the DetectSoftError mechanism
    return
    myLogger.info("Triggering DetectSoftError mechanism in run {0}".format(runNumber))
    lastDetSoftErrLumi = lumiRun
    try:
        r = requests.get('{0}{1}'.format(pixelSupervisorBaseUrl,
                                      pixelSupervisorHandler), params=pixelSupervisorPayload)
        myLogger.info("Calling the following URL: {0}".format(r.url))
        myLogger.info("Response from PixelSupervisor: {0}".format(r.status_code))
    except requests.exceptions.RequestException as e:
        myLogger.error("Request error: {0}".format(e))
    # just to be safe, wait a bit before continuing
    sleep(60)


def startTimer():
    # it auto-starts, no need of rt.start()
    myLogger.info('Calling status loop every {0} seconds.'.format(timeOut))
    myLogger.info('Integrated luminosity threshold is {0} pb-1'.format(lumiThreshold))
    rt = RepeatedTimer(timeOut, statusLoop)


if __name__ == "__main__":
    myLogger.info('Creating new log file - closing this one.')
    myLogger.handlers[0].doRollover()
    myLogger.info('You are running version {0}.'.format(currentVersion))
    myLogger.info('Starting application')
    startTimer()
