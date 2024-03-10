#!/usr/bin/env python3
"""

@author    :  Shane Bradley
@contact   :  sbradley@redhat.com
@version   :  2.17
@copyright :  GPLv2
"""
import os.path
import logging
import mimetypes
import subprocess
import shutil

import sx
from sx.logwriter import LogWriter
from sx.extractors import Extractor

class Tarextractor(Extractor) :
    def __init__(self, pathToFile):
        Extractor.__init__(self, "TARextractor", pathToFile, "/bin/tar")

    def isCommandInstalled(self) :
        command = [self.getPathToCommand(), "--version"]
        try :
            tarTask = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdout, stderr) = tarTask.communicate()
            # Decode a bytes like object into a string
            if isinstance(stdout, bytes):
                stdout = stdout.decode()
            if ((stdout.find("GNU") >= 0) or (tarTask.returncode  == 0)):
                return True
            else:
                return False
        except OSError:
            message = "There was an error checking if the binary tar is installed."
            logging.getLogger(sx.MAIN_LOGGER_NAME).error(message)
            return False

    def isValidMimeType(self):
        mimetypes.init()
        mimetypes.encodings_map[".xz"] = "xz"

        # Returns a tuple of [type, encoding]: (index 0 = type), (index 1 = encoding)
        mimeType = mimetypes.guess_type(self.getPathToFile())
        if ((mimeType[0] == "application/x-tar") and ((mimeType[1] == "gzip") or (mimeType[1] == "bzip2"))):
            # For now will assume that it is a tar.gz or tar.bz2 file. Will not use "tarfile" checker.
            return True
        elif ((mimeType[0] == "application/x-tar") and (mimeType[1] == "xz")):
            # For now will assume that it is a tar.xz file
            return True
        elif ((mimeType[0] == "application/x-tar") and (mimeType[1] == None)):
            # For now will assume that it is a tar file with no compression
            return True
        return False

    def getListArgs(self) :
        if (not self.isValidMimeType()):
            return None;
        compressionType = mimetypes.guess_type(self.getPathToFile())[1]
        if (compressionType in ["gzip", "bzip2", "xz"]):
            return "atf"
        elif (compressionType == None):
            return "tf"
        return None

    def getExtractArgs(self) :
        if (not self.isValidMimeType()):
            return None;
        compressionType = mimetypes.guess_type(self.getPathToFile())[1]
        if (compressionType in ["gzip", "bzip2", "xz"]):
            return "axpf"
        elif (compressionType == None):
            return "xpf"
        return None

    # ###########################################################################
    # Extract, list, getDataFromFile functions
    # ###########################################################################
    def getDataFromFile(self, pathToFileInExtractor) :
        # Get the path that is contained in the tarball, since path
        # that is passed to function is relative path.
        fileList =  self.list()
        fullPathToFile = ""
        for item in fileList:
            # Decode bytes like object to str
            if isinstance(item, bytes):
                item = item.decode()
            splitItem = item.split("/", 1)
            # Strip any leading slashes because the result will not
            # contain one.
            if (len(splitItem) == 1):
                if (splitItem[0] == pathToFileInExtractor.strip("/")):
                    fullPathToFile = item
                    break;
            elif (len(splitItem) >= 2):
                if (splitItem[1] == pathToFileInExtractor.strip("/")):
                    fullPathToFile = item
                    break;
        # Get the options to extract
        commandOptions = self.getExtractArgs()
        if (commandOptions == None) :
            message =  "This file is unknown type and will not be extracted: %s." %(self.getPathToFile())
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
        elif (not len(fullPathToFile) > 0):
            message = "The path to the file does not exist: %s" %(pathToFileInExtractor)
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
        else:
            # ###################################################################
            # Create a tmp directory to extract the file
            # ###################################################################
            if (not os.access(Extractor.PATH_TO_TEMP_DIR, os.F_OK)):
                try:
                    os.makedirs(Extractor.PATH_TO_TEMP_DIR)
                except (IOError, os.error):
                    message = "Could not create the directory to extract file to: %s" % (Extractor.PATH_TO_TEMP_DIR)
                    logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
            command = [self.getPathToCommand(), commandOptions, self.getPathToFile(), "-C", Extractor.PATH_TO_TEMP_DIR, "--strip-components", "0", fullPathToFile]
            task = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdout, stderr) = task.communicate()
            if (not task.returncode  == 0):
                message = "There was an error extracting a file from the file: %s." % (self.getPathToFile())
                logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
            else:
                fileExtractedContents = []
                pathToExtractedFile = os.path.join(Extractor.PATH_TO_TEMP_DIR, fullPathToFile)
                # Extract the contents of the file to an array
                if (os.path.isfile(pathToExtractedFile)):
                    try:
                        fout = open(pathToExtractedFile, "r")
                        fileExtractedContents = fout.readlines()
                        fout.close
                    except (IOError, os.error, KeyError):
                        message = "There was a problem reading a file that was extracted from a tarfile: %s" %(pathToExtractedFile)
                        logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
                return fileExtractedContents
        return []

    def extract(self, extractDir, stripDirectoriesDepth=1) :
        commandOptions = self.getExtractArgs()
        if (commandOptions == None) :
            message =  "This file is unknown type and will not be extracted: %s." %(self.getPathToFile())
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
        elif (not self.isCommandInstalled()):
            message = "The %s command does not appear to be installed or incorrect version." %(self.getPathToCommand())
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
        else:
            # Add in all files that should be excluded. Add exclude string so
            # that certain large files are skipped like /var/account. An option
            # will need to be added to sx, report classes, and extractors. Will
            # need to build up the string if multiples. Need to test cause it
            # did not work before but appears to be good idea.
            excludedFiles = ""
            #excludedFiles = " --exclude=\"var/account/p*\""
            message = "%s %s %s -C %s --strip-components %s %s" %(self.getPathToCommand(), commandOptions, self.getPathToFile(), extractDir, str(stripDirectoriesDepth), excludedFiles)
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
            command = [self.getPathToCommand(), commandOptions, self.getPathToFile(), "-C", extractDir, "--strip-components", str(stripDirectoriesDepth), excludedFiles]
            task = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdout, stderr) = task.communicate()
            if (not task.returncode  == 0):
                message = "There was an error extracting the file: %s." % (self.getPathToFile())
                logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)
            else:
                return os.path.isdir(extractDir)
        return False

