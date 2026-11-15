
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet, ether_types
from os_ken.lib import hub


class BandwidthController(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(BandwidthController, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapaths = {}
        self.previous_stats = {}

        self.monitor_thread = hub.spawn(self._monitor)

    def add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(flow_mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        self.datapaths[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(datapath, 0, match, actions)

        self.logger.info(
            "Switch connected: %016x", datapath.id
        )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(
            dst, ofproto.OFPP_FLOOD
        )

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst
            )
            self.add_flow(datapath, 1, match, actions)

        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )

        datapath.send_msg(out)

    def _monitor(self):
        while True:
            for datapath in list(self.datapaths.values()):
                parser = datapath.ofproto_parser

                request = parser.OFPFlowStatsRequest(datapath)
                datapath.send_msg(request)

            hub.sleep(5)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        now = time.monotonic()

        for stat in ev.msg.body:

            if stat.priority == 0:
                continue

            key = (
                dpid,
                stat.table_id,
                stat.priority,
                str(stat.match)
            )

            current_bytes = stat.byte_count
            previous = self.previous_stats.get(key)

            if previous is None:
                self.previous_stats[key] = (
                    current_bytes, now
                )
                continue

            old_bytes, old_time = previous

            elapsed = now - old_time
            byte_difference = current_bytes - old_bytes

            if elapsed > 0 and byte_difference >= 0:
                throughput = (
                    byte_difference * 8
                    / elapsed
                    / 1_000_000
                )

                self.logger.info(
                    "FLOW_STATS | Switch=%016x | "
                    "Packets=%d | Bytes=%d | "
                    "Bandwidth=%.3f Mbps",
                    dpid,
                    stat.packet_count,
                    current_bytes,
                    throughput
                )

            self.previous_stats[key] = (
                current_bytes, now
            )

