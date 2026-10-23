#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: CARAT Replay Source
# Author: CARAT
# Description: Replay a recorded IQ session (SigMF-format .sigmf-data, raw interleaved complex64) over ZMQ PUB for hardware-free downstream development.
# GNU Radio version: 3.10.9.2

from gnuradio import blocks
import pmt
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import zeromq




class replay_source(gr.top_block):

    def __init__(self, iq_file='', samp_rate=250000, zmq_addr='tcp://127.0.0.1:5555', repeat='False'):
        gr.top_block.__init__(self, "CARAT Replay Source", catch_exceptions=True)

        ##################################################
        # Parameters
        ##################################################
        self.iq_file = iq_file
        self.samp_rate = samp_rate
        self.zmq_addr = zmq_addr
        self.repeat = repeat

        ##################################################
        # Blocks
        ##################################################

        self.zeromq_pub_sink_0 = zeromq.pub_sink(gr.sizeof_gr_complex, 1, zmq_addr, 100, False, (-1), '', True, True)
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_gr_complex*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_file_source_0 = blocks.file_source(gr.sizeof_gr_complex*1, iq_file, True, 0, 0)
        self.blocks_file_source_0.set_begin_tag(pmt.PMT_NIL)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.blocks_file_source_0, 0), (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.zeromq_pub_sink_0, 0))


    def get_iq_file(self):
        return self.iq_file

    def set_iq_file(self, iq_file):
        self.iq_file = iq_file
        self.blocks_file_source_0.open(self.iq_file, True)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.blocks_throttle2_0.set_sample_rate(self.samp_rate)

    def get_zmq_addr(self):
        return self.zmq_addr

    def set_zmq_addr(self, zmq_addr):
        self.zmq_addr = zmq_addr

    def get_repeat(self):
        return self.repeat

    def set_repeat(self, repeat):
        self.repeat = repeat



def argument_parser():
    description = 'Replay a recorded IQ session (SigMF-format .sigmf-data, raw interleaved complex64) over ZMQ PUB for hardware-free downstream development.'
    parser = ArgumentParser(description=description)
    parser.add_argument(
        "--iq-file", dest="iq_file", type=str, default='',
        help="Set IQ file path [default=%(default)r]")
    parser.add_argument(
        "--samp-rate", dest="samp_rate", type=eng_float, default=eng_notation.num_to_str(float(250000)),
        help="Set Sample rate (sps) [default=%(default)r]")
    parser.add_argument(
        "--zmq-addr", dest="zmq_addr", type=str, default='tcp://127.0.0.1:5555',
        help="Set ZMQ PUB address [default=%(default)r]")
    parser.add_argument(
        "--repeat", dest="repeat", type=str, default='False',
        help="Set Repeat file [default=%(default)r]")
    return parser


def main(top_block_cls=replay_source, options=None):
    if options is None:
        options = argument_parser().parse_args()
    tb = top_block_cls(iq_file=options.iq_file, samp_rate=options.samp_rate, zmq_addr=options.zmq_addr, repeat=options.repeat)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
