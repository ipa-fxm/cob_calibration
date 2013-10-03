# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import numpy
from numpy import matrix, vsplit, sin, cos, reshape, zeros, pi, isnan, isinf, array, arctan
import rospy
import tf.transformations

class SingleTransform:
    def __init__(self, config = zeros((6,1))):
        assert(len(config) == 6)

        eval_config = [eval(str(x)) for x in config]

        self._config = array(reshape(matrix(eval_config, float), (-1,1)))

        try:
            rospy.logdebug("Initializing single transform with params [%s]", ", ".join(["% 2.4f" % x[0] for x in eval_config]))
        except:
            rospy.logdebug("Initializing single transform with params [%s]", ", ".join(["% 2.4f" % x for x in eval_config]))
        self.inflate(self._config)

    def calc_free(self, free_config):
        assert( len(free_config) == 6 )
        return [x == 1 for x in free_config]


    def params_to_config(self, param_vec):
        assert(param_vec.shape == (6,1))
        return param_vec.T.tolist()[0]

    # Convert column vector of params into config/home/fmw-ja/.ros/test_results/cob_robot_calibration_est/TEST-test_SingleTransform.xml
    def inflate_rpy(self, p, ret=False):
        assert(p.size == 6)
        T=tf.transformations.compose_matrix(angles=[p[3,0],p[4,0],p[5,0]],translate=[p[0,0],p[1,0],p[2,0]])

        self.transform = T
        if ret:
            return T
    def inflate_new(self,p,ret=False):

        '''
        complex calculation of 4x4 homogeneus transformation matrix by Willow Garage Inc.
        for simplification with use of tf see inflate(self,p)
        '''
        #p=reshape(matrix([eval(str(x))for x in p],float),(-1,1))



        # Init output matrix
        T = matrix( zeros((4,4), float ))


        # Renormalize the rotation axis to be unit length
        a = tf.transformations.unit_vector(p[3:6])
        rot_angle= tf.transformations.vector_norm(p[3:6])


        # Built rotation matrix
        c = cos(rot_angle) ;
        s = sin(rot_angle) ;

        R = tf.transformations.rotation_matrix(rot_angle,a)
        T= R ;
        T[0,3] = p[0]
        T[1,3] = p[1]
        T[2,3] = p[2]
        self.transform = T
        if ret:
            return T
    def inflate(self,p, ret=False):

        '''
        complex calculation of 4x4 homogeneus transformation matrix by Willow Garage Inc.
        for simplification with use of tf see inflate(self,p)
        '''
        p = array(p)
        p=reshape(matrix([eval(str(x))for x in p],float),(-1,1))



        # Init output matrix
        T = matrix( zeros((4,4), float ))
        T[3,3] = 1.0

        # Copy position into matrix
        T[0:3,3] = p[0:3]

        # Renormalize the rotation axis to be unit length
        U,S,Vt = numpy.linalg.svd(p[3:6])
        a = U[:,0]
        rot_angle= S[0]*Vt[0,0]


        # Built rotation matrix
        c = cos(rot_angle) ;
        s = sin(rot_angle) ;

        R = matrix( [ [   a[0,0]**2+(1-a[0,0]**2)*c, a[0,0]*a[1,0]*(1-c)-a[2,0]*s, a[0,0]*a[2,0]*(1-c)+a[1,0]*s],
                      [a[0,0]*a[1,0]*(1-c)+a[2,0]*s,    a[1,0]**2+(1-a[1,0]**2)*c, a[1,0]*a[2,0]*(1-c)-a[0,0]*s],
                      [a[0,0]*a[2,0]*(1-c)-a[1,0]*s, a[1,0]*a[2,0]*(1-c)+a[0,0]*s,    a[2,0]**2+(1-a[2,0]**2)*c] ] )

        T[0:3,0:3] = R ;
        self.transform = T
        if ret:
            return T

    # Take transform, and convert into 6 param vector
    def deflate_rpy(self):
        scale,shear,angles,transl,persp=tf.transformations.decompose_matrix(self.transform)
        config=list(transl)+list(angles)
        c=[[v] for v in config]
        self._config=c
        return self._config
    def deflate(self):
        T = self.transform
        if isnan(self.transform).any() or isinf(self.transform).any():
            v = [0,0,0]
        else:
            angle, direction, point = tf.transformations.rotation_from_matrix(self.transform)
            v = angle * direction
        return matrix([T[0,3],T[1,3],T[2,3], v[0], v[1], v[2]]).T

    # Returns # of params needed for inflation & deflation
    def get_length(self):
        return 6

