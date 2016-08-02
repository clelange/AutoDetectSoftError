# AutoDetectSoftError

This tools allows to automatically run DetectSoftError for the CMS pixel detector once a certain amount of integrated luminosity has been delivered by the LHC.

Within the P5 network run (suggest to use ```srv-c2f38-15-01.cms```):
```
python AutoDetectSoftError.py
```

Press ```Ctrl+C``` to quit.

Tested with python 2.6.6 (default on pixel machines).

For stable versions please refer to the [releases tab](releases).

## Settings

Settings can be found on top of the file (might switch to ArgParse later):

| Variable | Default value | explanation |
| -------- | ------------- | ----------- |
| timeOut  | 30            | set time out for the query, i.e. at which frequency the check is performed |
| lumiThreshold | 100.0    | integrated luminosity threshold in 1/pb |
| lastDetSoftErrLumi | 0   | last int. lumi value DetectSoftError has been called (this should generally not be changed) |
