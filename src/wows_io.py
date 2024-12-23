import copy as CP
import xml.etree.ElementTree as ET
import itertools as ITR
import json as JSON
import os as OS
import pathlib as PTH
import shutil as SHU

import jinja2 as JJ
import polib as PO
import wowsunpack as WUP


class NamelessRecipientError(ValueError):
    pass


class PortraitlessRecipientError(ValueError):
    pass


voice_xml_template = JJ.Template("""
<AudioModification.xml>
\t<AudioModification>
\t\t<Name>{{mod_name}}</Name>
{% for external_event_name in event_names %}
\t\t<ExternalEvent>
\t\t\t<Name>{{external_event_name}}</Name>
\t\t\t<Container>
\t\t\t\t<Name>Voice</Name>
\t\t\t\t<ExternalId>{{"V" + external_event_name[5:]}}</ExternalId>
\t\t\t</Container>
\t\t</ExternalEvent>
{% endfor %}
\t</AudioModification>
</AudioModification.xml>
""")


class WowsIo:

    def __init__(self, wows_dir, wows_lang):
        self.language = wows_lang
        self.unpacker = WUP.WoWsUnpack(wows_dir)
        self.version_dir = PTH.Path(wows_dir, "bin", self.unpacker._findLatestBinFolder())
        self.working_dir = PTH.Path(OS.getcwd())
        self.mo = PO.mofile(PTH.Path(self.version_dir, "res", "texts",
                                     wows_lang, "LC_MESSAGES", "global.mo"))
        self.unpacker.unpackGameParams()
        self.unpacker.decodeGameParams()
        self.unpacker.unpack("gui/crew_commander/base/*/*.png")
        self.unpacker.unpack("banks/ModBuilderSettings.xml")

    def fetch_recipients(self):
        recipients = []
        with open("GameParams-0.json") as game_params_json:
            game_params = JSON.load(game_params_json)
        for value in game_params.values():
            if value["typeinfo"]["type"] == "Crew" and value["CrewPersonality"]["isPerson"]:
                try:
                    recipient = RecipientCommander(value["CrewPersonality"]["personName"],
                                                   value["CrewPersonality"]["ships"]["nation"],
                                                   value["CrewPersonality"]["subnation"],
                                                   value["CrewPersonality"]["peculiarity"],
                                                   value["CrewPersonality"]["hasOverlay"],
                                                   self.mo)
                except NamelessRecipientError:
                    print(f"Skipping recipient commander without name in language {self.language}:",
                          f"{value["CrewPersonality"]["personName"]}.")
                except PortraitlessRecipientError:
                    print(f"Skipping recipient commander without portrait: {value["CrewPersonality"]["personName"]}.")
                else:
                    recipients.append(recipient)
        return recipients

    def fetch_donor_voices(self):
        voices = set()
        xml = ET.parse(PTH.Path("banks", "ModBuilderSettings.xml"))
        for match in ITR.chain(
         xml.findall("./OneCaptain/state[@name='CrewName']"),
         xml.findall("./MultiCaptain/stateValuesList/stateValue"),
         xml.findall("./PolyglotCaptain/state[@name='CreName']")):
            voice = match.attrib["value"]
            if voice in voices:
                print(f"Voice name collision detected: {voice}.")
            voices.add(voice)
        return sorted(voices, key=lambda s: s.lower())

    def install_voices(self, changes, mod_name="Special Commander Customizer", mod_id="SCC"):
        if not changes:
            return
        self.unpacker.unpack("banks/OfficialMods/*/mod.xml")
        mod_dir = self.version_dir / PTH.Path("res_mods", "banks", "Mods", mod_id)
        OS.makedirs(mod_dir, exist_ok=False)

        events = {}
        xpaths = ["./AudioModification/ExternalEvent/Container/Path/StateList" +
                  f"/State[Name='CrewName'][Value='{donor_name}']"
                  for donor_name in set(changes.values())]
        for donor_mod in (self.working_dir / PTH.Path("banks", "OfficialMods")).iterdir():
            xml = ET.parse(donor_mod / "mod.xml")
            donor_mod_id = donor_mod.name

            # Remap audio files.
            for xpath in xpaths:
                for file_name in xml.findall(xpath + "/../../FilesList/File/Name"):
                    file_name.text = f"../../OfficialMods/{donor_mod_id}/{file_name.text}"

            event_nodes = set()
            for xpath in xpaths:
                event_nodes.update(xml.findall(xpath + "/../../../.."))
            for event in event_nodes:
                event_name = event.find("./Name").text
                external_id = event.find("./Container/ExternalId").text
                assert "V" + event_name[5:] == external_id and "Play_" + external_id[1:] == event_name, \
                    "Failed to derive correspondence between ExternalId and ExternalEvent/Name"
                if event_name not in events:
                    # Register event. Corresponding events from all mod files will be merged into this list.
                    events[event_name] = []
                for path in event.findall("./Container/Path"):
                    name = path.find("./StateList/State[Name='CrewName']/Value").text
                    for recipient_name, donor_name in changes.items():
                        if donor_name == name:
                            # Copy is required for supporting multiple recipients with same voice.
                            new_path = CP.deepcopy(path)
                            new_path.find("./StateList/State[Name='CrewName']/Value").text = recipient_name
                            events[event_name].append(new_path)

        for paths in events.values():
            paths.sort(key=lambda p: p.find("./StateList/State[Name='CrewName']/Value").text)
        out_xml = ET.fromstring(voice_xml_template.render(mod_name=mod_name, event_names=sorted(events.keys())))
        for container in out_xml.findall("./AudioModification/ExternalEvent/Container"):
            container.extend(events["Play_" + container.find("./ExternalId").text[1:]])
        ET.ElementTree(out_xml).write(mod_dir / "mod.xml")

    def install_portraits(self, changes):
        if not changes:
            return
        mod_dir = self.version_dir / PTH.Path("res_mods", "gui", "crew_commander", "base")
        for recipient, donor in changes.items():
            absolute_recipient = mod_dir / recipient
            OS.makedirs(absolute_recipient.parent)
            SHU.copyfile(donor, absolute_recipient)


class RecipientCommander:

    def __init__(self, code_name, nations, subnation, peculiarity, has_overlay, mo):
        if not subnation and nations:
            subnation = nations[0]
        self.portrait_path = PTH.Path("gui", "crew_commander", "base", subnation, f"{code_name}.png")
        if not self.portrait_path.is_file():
            raise PortraitlessRecipientError()
        self.translation_id = f"IDS_{code_name.upper()}"
        for entry in mo:
            if entry.msgid == self.translation_id:
                self.name = entry.msgstr
                break
        else:
            raise NamelessRecipientError()
        self.peculiarity = peculiarity
        self.has_overlay = has_overlay

    def __str__(self):
        return f"(Recipient) {self.name}"


def main():
    with open("../session.json") as session_json:
        session = JSON.load(session_json)
    io = WowsIo(session["wows_dir"], session["wows_lang"])


if __name__ == "__main__":
    main()
