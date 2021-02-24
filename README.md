# HA-teleinfo

Home assistant sensor for EDF teleinfo.

First implementation for uTeleinfo USB Dongle from Charles Hallard (https://www.tindie.com/products/hallard/micro-teleinfo-v20/).

Feel free to PR, fork or anything else.

## How to use

Add to your configuration.yml

```yaml
- platform: teleinfo
  resources:
    - iinst
    - imax
    - papp
    - ptec
```


