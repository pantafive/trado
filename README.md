# trado
Dumb and dirty docker-compose files generator for traefik exposing

All services described in one services.yml file and converted to more or less docker-compose compatible blocks. 
Top-level keys is services name, images, environment, volumes, ports is mirrored to docker-compose.
Important part is `url` key, which is used to generate traefik labels.
`url` signature is:
```yaml
url: <host>[/<path>][@port]
```

- `host` directly used as hostname in traefik labels. TLS with letsencrypt is enabled by default.
- `path` is optional and used as path in traefik. New service will be exposed with `https://host/path` but after proxing the path will be truncated.
   Be careful, `host` without path must be configured in a diffrenent service at least once.
- `port`: it's a hint for traefik to find a proper port for proxying

Notice, that default `networks` for all services with `url` defined is `traefik`.

```yaml
gitea:
  image: gitea/gitea:latest
  append:
    environment:
      - USER_UID=1000
      - USER_GID=1000
    volumes:
      - ./data:/data
    ports:
      - "3000:3000"
      - "2222:22"
  url: git.rubedo.cloud @ 3000
  expose: 3000
asdf:
  image: containous/whoami
  url: asdf.rubedo.cloud
whoami2:
  image: containous/whoami
  url: git.rubedo.cloud /test
  append:
    restart: unless-stopped
    labels:
      - "testlabel=true"
blah:
  image: containous/whoami # not exposed to traefik at all
```