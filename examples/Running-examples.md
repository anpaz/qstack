Steps:

1. Install qstack from source
   `pip install -e .`

2. Run quilc and Rigetti's QVM using Docker:

```
docker run --rm -it -p 5555:5555 rigetti/quilc -P -S
docker run --rm -it -p 5000:5000 rigetti/qvm -S
```

> The QVM uses port 5000, which is used by Airplay Receiver in a Mac, so manually turn it off (see https://stackoverflow.com/questions/72369320/why-always-something-is-running-at-port-5000-on-my-mac)
