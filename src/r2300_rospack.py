#!/usr/bin/env python3

'''
Pepperl-Fuchs  R2300  ROS driver
Frame id:R2300_datas
Topic:R2300/data(msg type:LaserScan, output:layer2)
test on ros_indigo python3

author: Ding Yi
email:l20031018@126.com

'''
import os
path = os.getcwd()
print(path)
os.chdir(path+'/src/r2300_rospack/src/')
import rospy
from sensor_msgs.msg import LaserScan, PointCloud2, PointField
import struct as st
import urllib.request
import configparser
import json
import socket
from threading import Thread, Lock
import queue as Queue
import random
import bisect
import t314314
import math

mute = Lock()
port = random.randint(16000, 19000)
q = Queue.Queue(200)
q1 = Queue.Queue(200)
#pc = PointCloud2()
#print (pc.header)
conf = configparser.ConfigParser()
conf.read('conf.ini')
ip = conf.get('ip_address', 'ip')
local_ip = conf.get('ip_address', 'local_ip')
selected_layer = int(conf.get('option', 'layer'))
request_handle = 'http://' + ip + '/cmd/request_handle_udp?address=' + local_ip + '&port=' + str(port) + '&packet_type=C1'
request_scanoutput = 'http://' + ip + '/cmd/start_scanoutput?handle='
set_f_l = 'http://' + ip + '/cmd/set_parameter?scan_frequency=50&pilot_enable=off'
release_handle = 'http://' + ip + '/cmd/release_handle?handle='


def getvalue(points,layer_index):
    distance = []
    intensities = []
    xyzi = []
    i = 0
    count = 0
    if layer_index == 2:
        angle_layer = 1.5
    elif layer_index == 3:
        angle_layer = -1.5
    elif layer_index == 1:
        angle_layer = -4.5
    else:
        angle_layer = -7.5
    #print (len(points[0:4]))
    angle_z = 90-angle_layer
    angle_x = -50
    
    while i < len(points):
        # here need to change from Spherical coordinate system to rectangular cartesian coordinate system
        s = st.unpack('<I',points[i:i+4])
        r = float(s[0]&0xfffff)/1000
        #intensities.append((s[0]>>20)&0xfff)
        #distance.append(float(s[0]&0xfffff)/1000)
        xyzi.append(((r*math.sin(math.radians(angle_z+6/1000*count)))*math.cos(math.radians(angle_x+0.1*count)), r*math.sin(math.radians(angle_z+6/1000*count))*math.sin(math.radians(angle_x+0.1*count)), r*math.cos(math.radians(angle_z+6/1000*count)), (s[0]>>20)&0xfff))
        i += 4
        count += 1
        #print('i',i)

        #print(r,xyzi[-1][0],xyzi[-1][1],xyzi[-1][2],layer_index,count)
        
            
        #print(xyzi)
    return xyzi

def pailie():
    global mute, q, selected_layer
    layer0 = []
    layer1 = []
    layer2 = []
    layer3 = []
    iS_layer_full = 0
    while iS_layer_full != 1:

        try:
            e = q.get()
        except:
            print ('q get error')
        if e[2] == 2 and len(layer2) < 4:
            bisect.insort_right(layer2, e)
            
        if e[2] == 0 and len(layer0) < 4:
            bisect.insort_right(layer0, e)            

        if e[2] == 1 and len(layer1) < 4:
            bisect.insort_right(layer1, e) 
           
        if e[2] == 3 and len(layer3) < 4:
            bisect.insort_right(layer3, e)            
            
        if len(layer2) == 4 and len(layer1) == 4  and len(layer0) == 4  and len(layer3) == 4:
            iS_layer_full = 1
    #print(len(layer2),len(layer1),len(layer3),len(layer0))

    return [[layer2[0][-1] + layer2[1][-1] + layer2[2][-1] + layer2[3][-1]], [layer3[0][-1] + layer3[1][-1] + layer3[2][-1] + layer3[3][-1]], [layer1[0][-1] + layer1[1][-1] + layer1[2][-1] + layer1[3][-1]], [layer0[0][-1] + layer0[1][-1] + layer0[2][-1] + layer0[3][-1]]]


def from_bytes(data):
    #print(len(data[0:58]),data[0:58])
    package_header = st.unpack('<HHIHHHHiQQIIHHHii',data[0:58])
    num_points_packet = package_header[12]
    layer_index = package_header[6]
    header_size = package_header[3]    #not sure
    angular_increment = package_header[-1]
    packet_number = package_header[5]
    scan_number = package_header[4]
    point = data[header_size:]
    first_index = package_header[14]
    first_angle = package_header[15]
    #print('layer index', layer_index)
    return [packet_number, scan_number, layer_index, num_points_packet, first_index, first_angle, angular_increment, point]


def request_datas():
    response = urllib.request.urlopen(set_f_l)
    response = urllib.request.urlopen(request_handle)
    j = response.read()
    result = json.loads(j)
    if result["error_code"] == 0 and result["error_text"] == 'success':
        handle = result['handle']
        response = urllib.request.urlopen(request_scanoutput+handle)
        j = response.read()
        result = json.loads(j)
        if result["error_code"] == 0 and result["error_text"] == 'success':
            print ('start scanoutput done')
        else:
            print ('fail @start scanoutput')
            
    else:
        print ('fail')


class ProducerThread(Thread):

    #def __init__(self):
    #    super(ProducerThread, self).__init__()
         

    def run(self):
        global local_ip, port, q
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((local_ip, port))
        print ('Bind UDP On Port %d..' %port)
        self.ring_buffer = b''
        while True:
            data, addr = s.recvfrom(2000) # here need to add to ring_buffer and use  magic bytes to find the start of packet
            #print(data.hex()[0:10])
            self.ring_buffer += data
            start_of_packet = self.ring_buffer.find(b'\x5c\xa2',0,len(self.ring_buffer))
            if start_of_packet != -1:
                packet_size = st.unpack('<I',self.ring_buffer[(start_of_packet+4):(start_of_packet+8)])[0]
                #print('packet_size', packet_size)
                
                
                q.put(from_bytes(self.ring_buffer[start_of_packet:(start_of_packet+packet_size+1)]))
                self.ring_buffer = self.ring_buffer[(start_of_packet+packet_size):]

class ConsumerThread(Thread):

    def run(self):
        global q, q1
        while True:
            s = pailie()  #s=[s2,s3,s1,s0]  s2 is list contain points of layer2 
            #print(s[0])
            s2 = getvalue(s[0][0],2)
            #q1.put(s2, False)
            s3 = getvalue(s[1][0],3)
            #q1.put(s3, False)
            s1 = getvalue(s[2][0],1)
            #q1.put(s1, False)
            s0 = getvalue(s[3][0],0)
            #q1.put(s0, False)
            #print('convert done',q1.qsize())
            
            try:
                q1.put((s2+s3+s1+s0), False)
                #print(q1.qsize())
            except:
                print('q1 put error')
                pass

if __name__ == '__main__':
    rospy.init_node("R2300_4")
    pub_data = rospy.Publisher('R2300/data', PointCloud2, queue_size=1)
    frame_id = rospy.get_param('~frame_id', 'R2300')
    frequency = rospy.get_param('frequency', 20)
    rate = rospy.Rate(frequency)
    seq = 0
    #pc.header.frame_id = frame_id
    #pc.angle_min = -0.872665
    #pc.angle_max = 0.872665
    #pc.angle_increment = 0.001745
    #pc.scan_time = 0.08
    #pc.range_min = 0.2
    #pc.range_max = 10
    request_datas()
    producer = ProducerThread()
    consumer = ConsumerThread()
    producer.start()
    #ProducerThread().join()
    consumer.start()
    #ConsumerThread().join()

    print (rospy.is_shutdown())
    while 1:
        try:
            #print('before get', q1.qsize())
            if q1.qsize()>0:
                #print('before get', q1.qsize())
                scans = q1.get(False)
                #print(len(scans))
                msg=t314314.array_to_xyzi_pointcloud2f(scans,None,'R2300',False)
                #print(msg)
            #pc.header.stamp = rospy.Time.now()
            #pc.header.seq = seq
            #pc.ranges = scans[0]
            #pc.intensities = scans[1]
                pub_data.publish(msg)
                seq += 1
            #rate.sleep()
        except:
            #print ('get from Q error',q1.qsize())
            pass

