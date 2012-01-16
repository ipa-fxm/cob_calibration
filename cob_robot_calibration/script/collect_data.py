#!/usr/bin/env python
PKG  = 'cob_auto_calibrate'
NODE = 'collect_data_node'
import roslib
roslib.load_manifest(PKG)
#roslib.load_manifest('pr2_calibration_executive')
#roslib.load_manifest('cob_script_server')
import rospy
import message_filters

from sensor_msgs.msg import *
from calibration_msgs.msg import *
from cob_image_capture.srv import *

from cv_bridge import CvBridge, CvBridgeError
from simple_script_server import simple_script_server

from cob_calibrate_camera import calibrate, cv2util

class DataCollector():
    '''
    @summary: Collects data for robot calibration.
    
    Subscribes to various topics needed (e.g. images, camera infos, joint angles) and 
    provides a service. When service is called, a set of samples is recorded, 
    processed (e.g. checkerboards are detected) and combined to a RobotMeasurement message 
    which is published as /robot_measurement.
    '''
    
    def __init__(self):
        '''
        Set up subscribers, publishers and local storage
        ''' 
        rospy.init_node(NODE)
        print "==> %s started " % NODE
        
        # get joint names for arm
        if rospy.has_param("arm_controller/joint_names"): # real hardware
            self.arm_joint_names = rospy.get_param("arm_controller/joint_names")
        elif rospy.has_param("arm_controller/joints"): # simulation
            self.arm_joint_names = rospy.get_param("arm_controller/joints")
        else: 
            print "Could not get joint names for arm from parameter server. exiting..."
            exit(-1)
            
        # get joint names for torso
        if rospy.has_param("torso_controller/joint_names"): # real hardware
            self.torso_joint_names = rospy.get_param("torso_controller/joint_names")
        elif rospy.has_param("torso_controller/joints"): # simulation
            self.torso_joint_names = rospy.get_param("torso_controller/joints")
        else: 
            print "Could not get joint names for torso from parameter server. exiting..."
            exit(-1)
        
        # CvBridge
        self.bridge = CvBridge() 
        
        #  init publisher / subscriber
        self._robot_measurement_pub = rospy.Publisher("/robot_measurement", RobotMeasurement)
        self._image_pub_left        = rospy.Publisher("/robot_measurement_image_left",  Image) #DEBUG
        self._image_pub_right       = rospy.Publisher("/robot_measurement_image_right", Image) #DEBUG
        self._image_pub_kinect_rgb  = rospy.Publisher("/robot_measurement_image_kinect_rgb", Image) #DEBUG
        self._sub_joint_states      = rospy.Subscriber( "/joint_states", JointState, self._callback_joints)
        
        # left camera
        self._sub_left_info         = message_filters.Subscriber("/stereo/left/camera_info", CameraInfo)
        self._sub_left_image_color  = message_filters.Subscriber("/stereo/left/image_rect_color", Image)
        self._sub_left_image_rect   = message_filters.Subscriber("/stereo/left/image_rect", Image)
        self._sub_left              = message_filters.TimeSynchronizer([self._sub_left_info, 
                                                                        self._sub_left_image_color, 
                                                                        self._sub_left_image_rect], 15)
        self._sub_left.registerCallback(self._callback_left)
        
        # right camera
        self._sub_right_info         = message_filters.Subscriber("/stereo/right/camera_info", CameraInfo)  
        self._sub_right_image_color  = message_filters.Subscriber("/stereo/right/image_rect_color", Image)
        self._sub_right_image_rect   = message_filters.Subscriber("/stereo/right/image_rect", Image)
        self._sub_right              = message_filters.TimeSynchronizer([self._sub_right_info, 
                                                                        self._sub_right_image_color, 
                                                                        self._sub_right_image_rect], 15)
        self._sub_right.registerCallback(self._callback_right)
        
        # kinect rgb
        self._sub_kinect_rgb_info         = message_filters.Subscriber("/cam3d/rgb/camera_info", CameraInfo)  
        self._sub_kinect_rgb_image_color  = message_filters.Subscriber("/cam3d/rgb/image_color", Image)
        self._sub_kinect_rgb              = message_filters.TimeSynchronizer([self._sub_kinect_rgb_info, 
                                                                        self._sub_kinect_rgb_image_color], 15)
        self._sub_kinect_rgb.registerCallback(self._callback_kinect_rgb)
        
        # initialize private members
        self._arm_joint_msg_received = False
        self._arm_joint_msg = None
        self._torso_joint_msg_received = False
        self._torso_joint_msg = None
        
        self._left = {}
        self._left_received = False
        self._right = {}
        self._right_received = False
        self._kinect_rgb = {}
        self._kinect_rgb_received = False
        
        self.counter = 1
        print "==> done with initialization"

    def _callback_left(self, camera_info, image_color, image_rect):
        '''
        Callback function for left camera message filter
        '''
        #print "DEBUG: callback left"
        self._left["camera_info"] = camera_info
        self._left["image_color"] = image_color
        self._left["image_rect"] = image_rect
        self._left_received = True
        
    def _callback_right(self, camera_info, image_color, image_rect):
        '''
        Callback function for right camera message filter
        '''
        #print "DEBUG: callback right"
        self._right["camera_info"] = camera_info
        self._right["image_color"] = image_color
        self._right["image_rect"] = image_rect
        self._right_received = True

    def _callback_kinect_rgb(self, camera_info, image_color):
        '''
        Callback function for kinect rgb message filter
        '''
        #print "DEBUG: callback kinect_rgb"
        self._kinect_rgb["camera_info"] = camera_info
        self._kinect_rgb["image_color"] = image_color
        self._kinect_rgb_received = True
    
    def _callback_joints(self, msg):
        '''
        Callback function for joint angles messages
        '''
        #print "DEBUG: callback joints"
        
        # torso
        if self.torso_joint_names[0] in msg.name:
            pos = []
            header = msg.header
            for name in self.torso_joint_names:
                pos.append(msg.position[msg.name.index(name)])

            # create JointState message
            joint_msg = JointState()
            joint_msg.header = msg.header
            joint_msg.name = self.torso_joint_names
            joint_msg.position = pos
            
            # safe joint state msg
            self._torso_joint_msg = joint_msg
            self._torso_joint_msg_received = True
        
        # arm
        if self.arm_joint_names[0] in msg.name:
            pos = []
            header = msg.header
            for name in self.arm_joint_names:
                pos.append(msg.position[msg.name.index(name)])

            # create JointState message
            joint_msg = JointState()
            joint_msg.header = msg.header
            joint_msg.name = self.arm_joint_names
            joint_msg.position = pos
            
            # safe joint state msg
            self._arm_joint_msg = joint_msg
            self._arm_joint_msg_received = True

    def run(self):
        '''
        Main method, starts service to provide capture functionality
        '''
        rospy.sleep(1)
        
        # Start service
        srv = rospy.Service('/image_capture/capture_images', CaptureImages, self._collect)
        rospy.loginfo("service of type 'CaptureImages' started under name '/image_capture/capture_images', waiting for requests...")
        rospy.spin()

    def _collect(self, data):
        '''
        Executed on service call. Logs and calls _capture_and_pub
        '''
        rospy.loginfo("capturing sample %.2i"%self.counter)
        res = self._capture_and_pub("sample%.2i"%self.counter, "cb_9x6", "arm_chain", (9,6))
        self.counter += 1
        return res

    def _capture_and_pub(self, sample_id, target_id, chain_id, pattern_size):
        '''
        Main capturing function. Gets a set of recent messages for all needed topics.
        Processes messages and creates RobotMeasuerment message which is published.
        
        @param sample_id: Sample identifier (e.g. sample01)
        @type  sample_id: string
        
        @param target_id: Name of checkerboard (e.g. cb_9x6)
        @type  target_id: string
        
        @param chain_id: Name of dh chain to which checkerboard is attached (e.g. arm_chain)
        @type  chain_id: string
        
        @param pattern_size: Size of checkerboard pattern as defined by opencv (e.g. (9, 6))
        @type  pattern_size: tuple(x, y)
        '''
        # capture measurements
        # --------------------
        self._left_received = False
        self._right_received = False
        self._kinect_rgb_received = False
        while (not self._left_received or not self._right_received or not self._kinect_rgb_received):
            rospy.sleep(0.005)
        latest_left = self._left
        latest_right = self._right
        latest_kinect_rgb = self._kinect_rgb
        
        self._torso_joint_msg_received = False
        self._arm_joint_msg_received = False
        while (not self._torso_joint_msg_received or not self._arm_joint_msg_received):
            rospy.sleep(0.005)
        latest_torso = self._torso_joint_msg
        latest_arm = self._arm_joint_msg
        
        # detect cb left
        # --------------
        cvImage = self.bridge.imgmsg_to_cv(latest_left["image_rect"], "mono8")
        image = cv2util.cvmat2np(cvImage)
        
        corners = calibrate._get_image_points(image, pattern_size)
        if corners != None:
            print "cb found: left"
            img_points_left = []
            for (x, y) in corners.reshape(-1, 2):
                img_points_left.append(ImagePoint(x, y))
        else:
            # cb not found
            return False
           
        # create camera msg left
        # ----------------------
        cam_msg_left = CameraMeasurement()
        cam_msg_left.camera_id = "left"
        cam_msg_left.header.stamp = latest_left["camera_info"].header.stamp
        cam_msg_left.cam_info     = latest_left["camera_info"]
        cam_msg_left.image_points = img_points_left
        cam_msg_left.verbose      = False
        #cam_ms_leftg.image        = latest_left["image_color"]
        #cam_msg_left.image_rect   = latest_left["image_rect"]
        #cam_msg_left.features    = # Not implemented here
        
        # detect cb right
        # --------------
        cvImage = self.bridge.imgmsg_to_cv(latest_right["image_rect"], "mono8")
        image = cv2util.cvmat2np(cvImage)
        
        corners = calibrate._get_image_points(image, pattern_size)
        if corners != None:
            print "cb found: right"
            img_points_right = []
            for (x, y) in corners.reshape(-1, 2):
                img_points_right.append(ImagePoint(x, y))
        else:
            # cb not found
            return False
           
        # create camera msg right
        # -----------------------
        cam_msg_right = CameraMeasurement()
        cam_msg_right.camera_id = "right"
        cam_msg_right.header.stamp = latest_right["camera_info"].header.stamp
        cam_msg_right.cam_info     = latest_right["camera_info"]
        cam_msg_right.image_points = img_points_right
        cam_msg_right.verbose      = False
        #cam_msg_right.image        = latest_right["image_color"]
        #cam_msg_right.image_rect   = latest_right["image_rect"]
        #cam_msg_right.features    = # Not implemented here

        # detect cb kinect_rgb
        # --------------------
        cvImage = self.bridge.imgmsg_to_cv(latest_kinect_rgb["image_color"], "mono8")
        image = cv2util.cvmat2np(cvImage)
        
        corners = calibrate._get_image_points(image, pattern_size)
        if corners != None:
            print "cb found: kinect_rgb"
            img_points_kinect_rgb = []
            for (x, y) in corners.reshape(-1, 2):
                img_points_kinect_rgb.append(ImagePoint(x, y))
        else:
            # cb not found
            return False
           
        # create camera msg kinect_rgb
        # ----------------------------
        cam_msg_kinect_rgb = CameraMeasurement()
        cam_msg_kinect_rgb.camera_id = "kinect_rgb"
        cam_msg_kinect_rgb.header.stamp = latest_kinect_rgb["camera_info"].header.stamp
        cam_msg_kinect_rgb.cam_info     = latest_kinect_rgb["camera_info"]
        cam_msg_kinect_rgb.image_points = img_points_kinect_rgb
        cam_msg_kinect_rgb.verbose      = False
        #cam_ms_kinect_rgbg.image        = latest_kinect_rgb["image_color"]
        #cam_msg_kinect_rgb.image_rect   = latest_kinect_rgb["image_rect"]
        #cam_msg_kinect_rgb.features    = # Not implemented here
        
        # create torso_chain msg
        # ----------------------
        torso_chain_msg = ChainMeasurement()
        torso_chain_msg.header = latest_torso.header
        torso_chain_msg.chain_id = "torso_chain"
        torso_chain_msg.chain_state = latest_torso
        
        # create arm_chain msg
        # --------------------
        arm_chain_msg = ChainMeasurement()
        arm_chain_msg.header = latest_arm.header
        arm_chain_msg.chain_id = "arm_chain"
        arm_chain_msg.chain_state = latest_arm
        
        # DEBUG publish pic
        # -----------------
        self._image_pub_left.publish(latest_left["image_color"])
        self._image_pub_right.publish(latest_right["image_color"])
        self._image_pub_kinect_rgb.publish(latest_kinect_rgb["image_color"])
        
        # create robot measurement msg and publish
        # -----------------
        robot_msg = RobotMeasurement()
        robot_msg.sample_id = sample_id
        robot_msg.target_id = target_id
        robot_msg.chain_id = chain_id
        robot_msg.M_cam = [cam_msg_left, cam_msg_right, cam_msg_kinect_rgb]
        robot_msg.M_chain = [torso_chain_msg, arm_chain_msg]
        self._robot_measurement_pub.publish(robot_msg)
        
        return True


if __name__ == "__main__":
    collector = DataCollector()
    collector.run()
