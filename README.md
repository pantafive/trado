# trado
Dumb and dirty docker-compose files generator for traefik exposing

All services described in one services.toml file and converted to more or less docker-compose compatible blocks. 
Top-level keys is services name, images, environment, volumes, ports is mirrored to docker-compose.

## Services exposure to traefik

The most complicated part is `public` key, which is used to generate traefik labels.
`public` signature is:
```yaml
public: <host>[/<path>][@port]
```

- `host` directly used as hostname in traefik labels. TLS with letsencrypt is enabled by default.
- `path` is optional and used as path in traefik. New service will be exposed with `https://host/path` but after proxing the path will be truncated.
   Be careful, `host` without path must be configured in a diffrenent service at least once.
- `port`: it's a hint for traefik to find a proper port for proxying

Notice, that default `networks` for all services with `public` defined is `traefik`.

## Options

- `image`: docker image name
- `envs`: list of environment variables
  - `doppler`: extract list of variables from [doppler](doppler.com/)
- `volumes`: list of volumes
- `ports`: list of ports
- `restart`: restart policy, default is `always`
- `networks`: list of networks. Default is `traefik` for every service with `public` defined but can be extended.
- `labels`: list of labels. For every `public` service it's filled with traefik-specific labels.
  - `watchtower`: add label to enable and disable autoupdate of service with [watchtower](https://github.com/containrrr/watchtower)
## Example

```toml
[gitea]
image = "gitea/gitea:latest"
public = "git.rubedo.cloud @ 3000"
doppler = true
wathctower = true
volumes = ["./data:/data"]

ports = ["3000:3000", "2222:22"]
    [gitea.envs]
    USER_UID = 1000
    USER_GID = 1000
    TEST = "test"

[asdf]
image = "containous/whoami"
public = "asdf.rubedo.cloud"
restart = "unless-stopped"

[whoami2]
image = "containous/whoami"
public = "git.rubedo.cloud /test"
restart = "unless-stopped"
labels = "testlabel=true"

[blah]
image = "containous/whoami" # not exposed to traefik at all
```