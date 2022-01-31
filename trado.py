#!/usr/bin/env python3
import pathlib
import yaml
import sys
from dataclasses import dataclass, field, asdict


SOURCE = "services.yml"
OUTPUT = "docker-compose.yml"


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
            res.append(yaml.dump({block: getattr(self, block)}, default_flow_style=False))
        return "\n".join(res)


@dataclass
class Trado:
    name: str = ""
    container_name: str = ""
    image: str = ""
    url_host: str = ""
    url_prefix: str = ""
    url_expose: int = 0
    labels: list[str] = field(default_factory=list)
    append: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(name: str, tr: dict) -> "Trado":
        gen = Trado(name=name)
        gen.image = tr.get("image", "")
        gen.url_host = tr.get("url", "")
        if gen.url_host:
            if '@' in gen.url_host:
                gen.url_host, gen.url_expose = [x.strip() for x in gen.url_host.rsplit("@",1)]
            if '/' in gen.url_host:
                gen.url_host, gen.url_prefix = [x.strip() for x in gen.url_host.split("/", 1)]
                gen.url_prefix = "/" + gen.url_prefix
        gen.container_name = tr.get("container_name", "")
        gen.append = tr.get("append", {})

        return gen

    def to_dict(self) -> dict:
        res = {}
        dt = asdict(self)
        del dt["name"]

        if self.url_host:
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
        if self.append:
            for k,v in self.append.items():
                if k in dt:
                    if type(dt[k]) is list:
                        dt[k] = dt[k] + v
                    elif type(dt[k]) is dict:
                        dt[k].update(v)
                    else:
                        raise TradoException(f"{k} is not a list or map, key confilict")
                else:
                    dt[k] = v
            del dt["append"]
        for k, v in dt.items():
            if v:
                res[k] = v
        for k in ["url_host", "url_prefix", "url_expose"]:
            if k in res:
                del res[k]
        return res


def main():
    srcpath = pathlib.Path(SOURCE)
    if not srcpath.exists():
        sys.stderr.write(f"Services: {SOURCE} not found\n")
        sys.exit(-1)
    output = OUTPUT
    if sys.argv[1:]:
        output = sys.argv[1]
    dstpath = pathlib.Path(output) if output != '--' else '--'
    if dstpath.exists() and dstpath.stat().st_mtime > srcpath.stat().st_mtime:
        sys.stderr.write(f"Services: {output} is same or newer than {SOURCE}, stop.\n")
        sys.exit(0)
    dc = DockerCompose()
    with open(srcpath, "r") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
        for service in data.keys():
            tr = Trado.from_dict(service, data[service])
            dc.services[service] = tr.to_dict()
    if dstpath == '-':
        print(dc.to_yaml())
    else:
        with open(dstpath, "w") as f:
            f.write(dc.to_yaml())
        print(f"{dstpath} file generated")
