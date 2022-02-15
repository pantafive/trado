#!/usr/bin/env python3
import pathlib
import yaml, tomli
import sys
import subprocess
from dataclasses import dataclass, field, asdict

DEFAULT_SOURCE = "services.toml"
DEFAULT_OUTPUT = "docker-compose.yml"


class TradoException(Exception):
    pass


@dataclass()
class DockerCompose:
    version: str = "3.8"
    services: dict = field(default_factory=dict)
    networks: dict = field(default_factory=lambda: {"traefik": {"external": True}})

    def to_yaml(self) -> str:
        res = []
        for block in "version,services,networks".split(","):
            if block == 'networks' and self.networks == {}:
                continue
            res.append(yaml.dump({block: getattr(self, block)}, default_flow_style=False))
        return "\n".join(res)


@dataclass
class Trado:
    name: str
    image: str = ""

    url_host: str = ""
    url_prefix: str = ""
    url_expose: int = 0

    labels: list[str] = field(default_factory=list)
    envs: list = field(default_factory=list)
    volumes: list = field(default_factory=list)
    ports: list = field(default_factory=list)
    restart: str = "always"

    doppler: bool = False
    watchtower: bool = False
    networks: list = field(default_factory=list)

    @staticmethod
    def from_dict(name: str, tr: dict) -> "Trado":
        gen = Trado(name=name)
        gen.image = tr.get("image", "")
        gen.get_url_host_splitted(tr)

        gen.labels = Trado.get_complex_by_type(tr, "labels")
        gen.envs = Trado.get_complex_by_type(tr, "envs")
        gen.volumes = Trado.get_complex_by_type(tr, "volumes")
        gen.ports = Trado.get_complex_by_type(tr, "ports")
        gen.networks = Trado.get_complex_by_type(tr, "networks")

        gen.restart = tr.get("restart", "always").lower()
        if gen.restart not in ["always", "on-failure", "unless-stopped", "no"]:
            raise TradoException(f"{gen.restart } is not a valid value for `restart` option")

        gen.doppler = tr.get("doppler", False)
        gen.watchtower = tr.get("watchtower", False)
        return gen

    def get_url_host_splitted(self, tr: dict):
        self.url_host = tr.get("public", "")
        if self.url_host:
            if '@' in self.url_host:
                self.url_host, self.url_expose = [x.strip() for x in self.url_host.rsplit("@", 1)]
            if '/' in self.url_host:
                self.url_host, self.url_prefix = [x.strip() for x in self.url_host.split("/", 1)]
                self.url_prefix = "/" + self.url_prefix

    @staticmethod
    def get_complex_by_type(tr: dict, element: str, flat: bool = False) -> list:
        item = tr.get(element, [])
        if type(item) is list:
            return item
        elif type(item) is dict:
            return [f"{k}={v}" for k, v in Trado.dict_to_dotted_notation(item).items()]
        elif type(item) is str:
            return [item]
        else:
            raise TradoException(f"`{element}` is not a list or map, key confilict")

    @staticmethod
    def dict_to_dotted_notation(d: dict) -> dict:
        res = {}
        for k, v in d.items():
            if isinstance(v, dict):
                for k2, v2 in Trado.dict_to_dotted_notation(v).items():
                    res[f"{k}.{k2}"] = v2
            else:
                res[k] = v
        return res

    def to_dict(self) -> dict:
        dt = asdict(self)
        del dt["name"]

        if self.url_host:
            self.add_network_labels(dt)
        else:
            dt["labels"] = []
        if self.doppler:
            self.add_doppler(dt)
        if not self.watchtower:
            self.add_watchtower_disabled(dt)

        if "envs" in dt:
            if "environment" not in dt:
                dt["environment"] = self.envs
            else:
                dt["environment"].extend(self.envs)
            del dt["envs"]
        for k in ["url_host", "url_prefix", "url_expose"]:
            if k in dt:
                del dt[k]
        return {k: v for k, v in dt.items() if v}

    def add_network_labels(self, dt):
        if "networks" in dt:
            dt["networks"].append("traefik")
        else:
            dt["networks"] = ["traefik"]
        labels: list[str] = ["enable=true"]
        if self.url_expose:
            labels.append(f"http.services.{self.name}.loadbalancer.server.port={self.url_expose}")
        rule = f"Host(`{self.url_host}`)" + (f" && PathPrefix(`{self.url_prefix}`)" if self.url_prefix else "")
        labels.append(f"http.routers.{self.name}.rule={rule}")
        labels.append(f"http.routers.{self.name}.entrypoints=web-secure")
        labels.append(f"http.routers.{self.name}.tls=true")
        if self.url_prefix:
            labels.append(f"http.middlewares.{self.name}-pathfix.stripprefix.prefixes={self.url_prefix}")
            labels.append(f"http.routers.{self.name}.middlewares={self.name}-pathfix@docker")
        else:
            labels.append(f"http.middlewares.{self.name}-https.redirectscheme.scheme=https")
            labels.append(f"http.routers.{self.name}-http.entrypoints=web")
            labels.append(f"http.routers.{self.name}-http.rule={rule}")
            labels.append(f"http.routers.{self.name}-http.middlewares={self.name}-https@docker")
            labels.append(f"http.routers.{self.name}.tls.certresolver=default")
        for line in labels:
            dt["labels"].append(f"traefik.{line}")

    def add_doppler(self, dt):
        doppler = subprocess.run("doppler secrets --json", shell=True, capture_output=True)
        if doppler.returncode == 0:
            dt["environment"] = [x for x in yaml.safe_load(doppler.stdout).keys() if not x.startswith('DOPPLER')]
        else:
            raise TradoException("doppler secrets --json failed")
        del dt["doppler"]

    def add_watchtower_disabled(self, dt):
        dt["labels"].append(f"com.centurylinklabs.watchtower.enable=false")
        del dt["watchtower"]


def make_dc_from_toml(srcpath):
    dc = DockerCompose()
    traefik_needed = False
    data = tomli.loads(srcpath.read_text())
    for service in data.keys():
        tr = Trado.from_dict(service, data[service])
        try:
            dc.services[service] = tr.to_dict()
        except TradoException as e:
            sys.stderr.write(f"Services: {service}: {e}\n")
            sys.exit(-5)
        if net := dc.services[service].get("networks", None):
            if "traefik" in net:
                traefik_needed = True
        if not traefik_needed:
            dc.networks = {}
    return dc


def main():
    output = " ".join(sys.argv[1:]) if sys.argv[1:] else DEFAULT_OUTPUT
    srcpath = pathlib.Path(DEFAULT_SOURCE)
    if not srcpath.exists():
        sys.stderr.write(f"Services: {DEFAULT_SOURCE} not found\n")
        sys.exit(-1)
    dstpath = pathlib.Path(output) if output != '-' else '-'
    if dstpath != '-' and dstpath.exists() and dstpath.stat().st_mtime > srcpath.stat().st_mtime:
        sys.stderr.write(f"Services: {output} is same or newer than {DEFAULT_SOURCE}, stop.\n")
        sys.exit(0)
    dc = make_dc_from_toml(srcpath)
    if dstpath == '-':
        print(dc.to_yaml())
    else:
        with open(dstpath, "w") as f:
            f.write(dc.to_yaml())
        print(f"{dstpath} file generated")
